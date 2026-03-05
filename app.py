"""
Dashboard IoT - Serveur Flask + Socket.IO
Déploiement : Render.com
"""

import os
import json
import threading
import time
import asyncio
from datetime import datetime, date
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_socketio import SocketIO, emit
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dashboard-secret-2024')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ─── CONFIG ────────────────────────────────────────────────────────────────────
PRONOTE_USER = os.environ.get('PRONOTE_USER', 'd.lecointre10')
PRONOTE_PASS = os.environ.get('PRONOTE_PASS', 'David@35160')
WEATHER_LAT  = os.environ.get('WEATHER_LAT', '48.1373')
WEATHER_LON  = os.environ.get('WEATHER_LON', '-1.9549')

# Cache en mémoire (Render = éphémère, pas de SQLite persistant)
_cache = {
    'pronote': {'notes_recentes': [], 'average': '--', 'emploi_du_temps': [], 'cantine': []},
    'sms': [],
    'pronote_ts': 0,
}
_cache_lock = threading.Lock()

# ─── HELPERS ───────────────────────────────────────────────────────────────────

def get_weather_emoji(code):
    codes = {
        0:'☀️',1:'🌤️',2:'⛅',3:'☁️',
        45:'🌫️',48:'🌫️',
        51:'🌦️',53:'🌦️',55:'🌧️',
        61:'🌧️',63:'🌧️',65:'🌧️',
        71:'🌨️',73:'🌨️',75:'🌨️',
        80:'🌦️',81:'🌧️',82:'⛈️',
        95:'⛈️',96:'⛈️',99:'⛈️'
    }
    return codes.get(code, '🌤️')

def get_weather_desc(code):
    codes = {
        0:'Ciel dégagé',1:'Peu nuageux',2:'Partiellement nuageux',3:'Couvert',
        45:'Brouillard',48:'Brouillard givrant',
        51:'Bruine légère',53:'Bruine',55:'Bruine dense',
        61:'Pluie légère',63:'Pluie',65:'Pluie forte',
        71:'Neige légère',73:'Neige',75:'Neige dense',
        80:'Averses',81:'Averses fortes',82:'Averses violentes',
        95:'Orage',96:'Orage avec grêle',99:'Orage violent'
    }
    return codes.get(code, 'Variable')

# ─── PRONOTE SCRAPER ───────────────────────────────────────────────────────────

def scrape_pronote():
    """Lance pronote_worker.py en subprocess pour éviter le conflit asyncio/gevent"""
    import subprocess, sys
    try:
        result = subprocess.run(
            [sys.executable, 'pronote_worker.py'],
            capture_output=True, text=True, timeout=180,
            env={**__import__('os').environ}
        )
        # Les prints du worker vont dans stderr (visible dans logs Render)
        if result.stderr:
            print(result.stderr, flush=True)
        if result.stdout:
            # Dernière ligne = JSON result
            lines = [l for l in result.stdout.strip().split('\n') if l]
            json_line = lines[-1] if lines else '{}'
            return json.loads(json_line)
        return {'notes_recentes': [], 'average': '0', 'error': 'Pas de sortie du worker'}
    except subprocess.TimeoutExpired:
        return {'notes_recentes': [], 'average': '0', 'error': 'Timeout 180s'}
    except Exception as e:
        return {'notes_recentes': [], 'average': '0', 'error': str(e)}


def _scrape_in_background():
    print('🔄 Scraping Pronote en arrière-plan...', flush=True)
    result = scrape_pronote()
    with _cache_lock:
        _cache['pronote'] = result
        _cache['pronote_ts'] = time.time()
        _cache['pronote_loading'] = False
    print(f'✅ Pronote OK: moyenne={result.get("average")} erreur={result.get("error","")}', flush=True)


def get_pronote_cached():
    """Lance le scraping en arrière-plan, retourne le cache immédiatement"""
    with _cache_lock:
        now = time.time()
        already_loading = _cache.get('pronote_loading', False)
        cache_stale = (now - _cache['pronote_ts'] > 1800) or not _cache['pronote']
        if cache_stale and not already_loading:
            _cache['pronote_loading'] = True
            t = threading.Thread(target=_scrape_in_background, daemon=True)
            t.start()
        return dict(_cache['pronote'])


# ─── ROUTES API ────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


@app.route('/api/data')
def api_data():
    """Données Pronote"""
    pronote = get_pronote_cached()
    with _cache_lock:
        loading = _cache.get('pronote_loading', False)
    return jsonify({'pronote': pronote, 'loading': loading})


@app.route('/api/scrape-now')
def api_scrape_now():
    """Force un nouveau scraping Pronote immédiatement"""
    with _cache_lock:
        _cache['pronote_ts'] = 0  # Invalide le cache
        _cache['pronote_loading'] = False
    pronote = get_pronote_cached()
    with _cache_lock:
        loading = _cache.get('pronote_loading', False)
    return jsonify({'message': 'Scraping lancé en arrière-plan', 'loading': loading})


@app.route('/api/weather-free')
def api_weather():
    """Météo Open-Meteo (gratuit, sans clé)"""
    try:
        url = (
            f'https://api.open-meteo.com/v1/forecast'
            f'?latitude={WEATHER_LAT}&longitude={WEATHER_LON}'
            f'&current_weather=true'
            f'&hourly=relativehumidity_2m,apparent_temperature'
            f'&timezone=Europe/Paris'
        )
        r = requests.get(url, timeout=10)
        d = r.json()
        cw = d.get('current_weather', {})
        code = cw.get('weathercode', 0)
        temp = round(cw.get('temperature', 0))

        # Humidité de l'heure actuelle
        hourly = d.get('hourly', {})
        humidity = '--'
        feel = temp
        if hourly.get('time'):
            now_str = datetime.now().strftime('%Y-%m-%dT%H:00')
            times = hourly['time']
            if now_str in times:
                idx = times.index(now_str)
                humidity = hourly.get('relativehumidity_2m', [None]*100)[idx]
                feel_val = hourly.get('apparent_temperature', [None]*100)[idx]
                if feel_val is not None:
                    feel = round(feel_val)

        return jsonify({
            'icon': get_weather_emoji(code),
            'temperature': f'{temp}°C',
            'condition': get_weather_desc(code),
            'humidity': humidity,
            'wind_speed': f"{round(cw.get('windspeed', 0))}km/h",
            'feel': feel,
        })
    except Exception as e:
        return jsonify({'error': str(e), 'temperature': '--', 'condition': 'Indisponible', 'icon': '🌤️'})


@app.route('/api/news-rss')
def api_news():
    """Actualités Le Monde via RSS"""
    try:
        r = requests.get('https://www.lemonde.fr/rss/une.xml', timeout=10,
                         headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(r.content, 'xml')
        items = soup.find_all('item')[:15]
        news = []
        for item in items:
            title = item.find('title')
            desc = item.find('description')
            news.append({
                'title': title.get_text(strip=True) if title else '',
                'summary': BeautifulSoup(desc.get_text(), 'html.parser').get_text(strip=True)[:300] if desc else '',
            })
        return jsonify(news)
    except Exception as e:
        return jsonify([])


@app.route('/api/cinema/programmation')
def api_cinema():
    """Programmation cinéma — stub JSON modifiable"""
    # À connecter à une vraie source si disponible
    return jsonify([])


# ─── AGENDA GOOGLE CALENDAR ────────────────────────────────────────────────────

@app.route('/api/calendar/events')
def api_calendar_events():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build

        token_path = '/tmp/token.json'
        creds_path = 'credentials.json'

        if not os.path.exists(token_path):
            if not os.path.exists(creds_path):
                return jsonify({'error': True, 'manual_auth': False,
                                'message': 'credentials.json manquant'})
            flow = Flow.from_client_secrets_file(creds_path,
                scopes=['https://www.googleapis.com/auth/calendar.readonly',
                        'https://www.googleapis.com/auth/tasks.readonly'])
            flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
            auth_url, _ = flow.authorization_url(prompt='consent')
            return jsonify({'error': True, 'manual_auth': True, 'auth_url': auth_url})

        creds = Credentials.from_authorized_user_file(token_path)
        service = build('calendar', 'v3', credentials=creds)

        today_start = datetime.now().replace(hour=0,minute=0,second=0,microsecond=0).isoformat()+'Z'
        today_end   = datetime.now().replace(hour=23,minute=59,second=59).isoformat()+'Z'

        events_result = service.events().list(
            calendarId='primary', timeMin=today_start, timeMax=today_end,
            singleEvents=True, orderBy='startTime'
        ).execute()

        events = []
        for e in events_result.get('items', []):
            start = e['start'].get('dateTime', e['start'].get('date', ''))
            end   = e['end'].get('dateTime', e['end'].get('date', ''))
            events.append({
                'id': e['id'],
                'type': 'event',
                'title': e.get('summary', 'Sans titre'),
                'start': start[11:16] if 'T' in start else start,
                'end':   end[11:16]   if 'T' in end   else end,
                'location': e.get('location', ''),
                'description': e.get('description', ''),
            })
        return jsonify({'events': events})

    except ImportError:
        return jsonify({'events': [], 'error': 'google-api-python-client non installé'})
    except Exception as e:
        return jsonify({'events': [], 'error': str(e)})


@app.route('/api/calendar/auth', methods=['POST'])
def api_calendar_auth():
    try:
        from google_auth_oauthlib.flow import Flow
        code = request.json.get('code', '').strip()
        flow = Flow.from_client_secrets_file('credentials.json',
            scopes=['https://www.googleapis.com/auth/calendar.readonly'])
        flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
        flow.fetch_token(code=code)
        with open('/tmp/token.json', 'w') as f:
            f.write(flow.credentials.to_json())
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/calendar/event/<event_id>', methods=['DELETE'])
def api_delete_event(event_id):
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds = Credentials.from_authorized_user_file('/tmp/token.json')
        service = build('calendar', 'v3', credentials=creds)
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# ─── SMS ───────────────────────────────────────────────────────────────────────

@app.route('/api/sms/wife')
def api_sms_wife():
    with _cache_lock:
        return jsonify(_cache['sms'])


@app.route('/api/sms/receive', methods=['POST'])
def api_sms_receive():
    """Reçoit un nouveau message (envoi ou réception externe)"""
    data = request.json or {}
    now = datetime.now().strftime('%H:%M')
    msg = {
        'sender': data.get('sender', 'Inconnu'),
        'message': data.get('message', ''),
        'time': now,
        'read': False,
    }
    with _cache_lock:
        _cache['sms'].append(msg)
        # Garder max 100 messages
        _cache['sms'] = _cache['sms'][-100:]
        sms_copy = list(_cache['sms'])

    # Notifier via WebSocket si message de la femme
    if 'Femme' in msg['sender'] or '💕' in msg['sender']:
        socketio.emit('urgent_alert' if '🚨' in msg['message'] else 'new_sms',
                      {'sender': msg['sender'], 'message': msg['message']})

    return jsonify({'success': True, 'total': len(sms_copy)})


@app.route('/api/sms/mark-read', methods=['POST'])
def api_sms_mark_read():
    with _cache_lock:
        for msg in _cache['sms']:
            msg['read'] = True
    return jsonify({'success': True})


@app.route('/api/sms/clear', methods=['POST'])
def api_sms_clear():
    with _cache_lock:
        _cache['sms'] = []
    return jsonify({'success': True})


# ─── IA CHAT ───────────────────────────────────────────────────────────────────

@app.route('/api/ai-chat')
def api_ai_chat():
    """Proxy vers Claude / OpenAI via Perplexity ou réponse simple"""
    q = request.args.get('q', '')
    api_key = os.environ.get('PERPLEXITY_API_KEY') or os.environ.get('OPENAI_API_KEY')

    if api_key:
        try:
            headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
            base = 'https://api.perplexity.ai' if os.environ.get('PERPLEXITY_API_KEY') else 'https://api.openai.com/v1'
            payload = {
                'model': 'sonar' if os.environ.get('PERPLEXITY_API_KEY') else 'gpt-3.5-turbo',
                'messages': [{'role': 'user', 'content': q}]
            }
            r = requests.post(f'{base}/chat/completions', json=payload, headers=headers, timeout=30)
            answer = r.json()['choices'][0]['message']['content']
            return jsonify({'answer': answer})
        except Exception as e:
            return jsonify({'answer': f'Erreur API IA: {e}'})

    return jsonify({'answer': 'Configurez PERPLEXITY_API_KEY ou OPENAI_API_KEY dans les variables d\'environnement Render.'})


# ─── WEBHOOK SMS EXTERNE ───────────────────────────────────────────────────────
# Permet à une app externe (ex: Android + Tasker/MacroDroid) d'envoyer des SMS reçus

@app.route('/webhook/sms', methods=['POST'])
def webhook_sms():
    """
    Webhook pour recevoir des SMS depuis un téléphone Android.
    Appeler depuis Tasker/MacroDroid avec :
    POST https://ton-app.onrender.com/webhook/sms
    Body JSON: { "sender": "Femme 💕", "message": "Salut !", "secret": "ton_secret" }
    """
    secret = os.environ.get('WEBHOOK_SECRET', 'change_me_secret')
    data = request.json or {}

    if data.get('secret') != secret:
        return jsonify({'error': 'Unauthorized'}), 401

    now = datetime.now().strftime('%H:%M')
    msg = {
        'sender': data.get('sender', 'Inconnu'),
        'message': data.get('message', ''),
        'time': now,
        'read': False,
    }

    with _cache_lock:
        _cache['sms'].append(msg)
        _cache['sms'] = _cache['sms'][-100:]

    # Émettre via WebSocket à tous les clients connectés
    socketio.emit('new_sms', {'sender': msg['sender'], 'message': msg['message']})

    # Alerte urgente si mots-clés
    urgent_keywords = ['urgent', 'vite', 'aide', 'descends', '🚨']
    if any(k in msg['message'].lower() for k in urgent_keywords):
        socketio.emit('urgent_alert', {'sender': msg['sender']})

    return jsonify({'success': True})


# ─── WEBSOCKET EVENTS ──────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    print(f'⚡ Client connecté: {request.sid}')
    emit('connected', {'status': 'ok'})

@socketio.on('disconnect')
def on_disconnect():
    print(f'❌ Client déconnecté: {request.sid}')


# ─── LANCEMENT ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
