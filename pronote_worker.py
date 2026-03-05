#!/usr/bin/env python3
"""
Pronote worker pour Render - SANS Chrome.
Utilise les cookies stockés dans la variable d'env PRONOTE_COOKIES (base64).
Si absent, tente Playwright en fallback.
"""
import json, os, base64, sys
from datetime import date, timedelta, datetime
import requests, pronotepy

PRONOTE_USER = os.environ.get('PRONOTE_USER', 'd.lecointre10')
PRONOTE_PASS = os.environ.get('PRONOTE_PASS', 'David@35160')
PRONOTE_BASE = 'https://0352235P.index-education.net/pronote/eleve.html'

def get_cookies_from_env():
    """Récupère les cookies depuis la variable PRONOTE_COOKIES (base64 JSON)"""
    b64 = os.environ.get('PRONOTE_COOKIES', '')
    if not b64:
        return None
    try:
        cookies_json = base64.b64decode(b64).decode()
        cookies_list = json.loads(cookies_json)
        print(f'COOKIES_ENV: {len(cookies_list)} cookies chargés', flush=True)
        return cookies_list
    except Exception as e:
        print(f'COOKIES_ENV_ERROR: {e}', flush=True)
        return None

def get_cookies_via_playwright():
    """Fallback: Playwright si pas de cookies en env"""
    from playwright.sync_api import sync_playwright
    print('PLAYWRIGHT: Login Toutatice...', flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox','--disable-setuid-sandbox',
                  '--disable-dev-shm-usage','--disable-gpu']
        )
        ctx = browser.new_context(locale='fr-FR', user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ))
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = ctx.new_page()

        page.goto('https://ent.toutatice.fr/portail/auth/', wait_until='domcontentloaded')
        page.wait_for_timeout(2000)
        page.click('button.card-button')
        page.wait_for_timeout(4000)
        page.wait_for_selector('#username', timeout=15000)
        page.click('#username', click_count=3)
        page.keyboard.type(PRONOTE_USER, delay=60)
        page.click('#password', click_count=3)
        page.keyboard.type(PRONOTE_PASS, delay=60)
        page.click('#bouton_valider')
        page.wait_for_timeout(5000)

        if 'e1s3' in page.url:
            try:
                page.click('button[type="submit"]')
                page.wait_for_timeout(5000)
            except: pass

        page.wait_for_url('**/portail/**', timeout=25000)
        page.wait_for_timeout(2000)
        page.wait_for_selector('[data-dnma-outil="PRONOTE"]', timeout=15000)

        try:
            with ctx.expect_page(timeout=8000) as np:
                page.click('[data-dnma-outil="PRONOTE"]')
            pronote_page = np.value
        except:
            page.click('[data-dnma-outil="PRONOTE"]')
            pronote_page = page
        pronote_page.wait_for_load_state('domcontentloaded')
        pronote_page.wait_for_timeout(3000)
        print(f'PLAYWRIGHT: Pronote → {pronote_page.url}', flush=True)

        cookies = ctx.cookies()
        browser.close()
        print(f'PLAYWRIGHT: {len(cookies)} cookies', flush=True)
        return cookies

def build_session(cookies_list):
    session = requests.Session()
    session.headers['User-Agent'] = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    )
    for c in cookies_list:
        session.cookies.set(
            c['name'], c['value'],
            domain=c.get('domain','').lstrip('.'),
            path=c.get('path','/')
        )
    return session

def scrape():
    try:
        # 1. Obtenir les cookies (env ou Playwright)
        cookies_list = get_cookies_from_env()
        if not cookies_list:
            print('COOKIES: pas de variable env, fallback Playwright', flush=True)
            cookies_list = get_cookies_via_playwright()

        session = build_session(cookies_list)

        def ent_func(username, password, **kwargs):
            return session.cookies

        # 2. Connexion pronotepy
        print('PRONOTEPY: connexion...', flush=True)
        client = pronotepy.Client(
            PRONOTE_BASE,
            username=PRONOTE_USER,
            password=PRONOTE_PASS,
            ent=ent_func
        )

        if not client.logged_in:
            return {'error': 'Cookies expirés - relance generate_cookies_for_render.py',
                    'notes_recentes': [], 'average': '0',
                    'emploi_du_temps': [], 'cantine': []}

        print(f'PRONOTEPY: {client.info.name}', flush=True)

        # 3. Notes Trimestre 2
        periods = client.periods
        trim2 = next((p for p in periods if 'Trimestre 2' in p.name), periods[0])
        notes_raw = []
        for g in trim2.grades:
            try:
                val  = float(str(g.grade).replace(',','.'))
                sur  = float(str(g.out_of).replace(',','.')) if g.out_of else 20.0
                n20  = round(val * 20 / sur, 2) if sur else val
                coef = float(str(g.coefficient).replace(',','.')) if g.coefficient else 1.0
                notes_raw.append({
                    'date_display': g.date.strftime('%-d %b') if g.date else '',
                    'matiere':      g.subject.name if g.subject else '?',
                    'intitule':     g.comment or '',
                    'note_brute':   f'{g.grade}/{int(sur)}',
                    'note_sur_20':  n20,
                    'moy_classe':   str(g.average) if g.average else '',
                    'coefficient':  coef,
                })
            except: pass

        avg = 0
        if notes_raw:
            tc  = sum(n['coefficient'] for n in notes_raw)
            avg = round(sum(n['note_sur_20']*n['coefficient'] for n in notes_raw)/tc, 2) if tc else 0
        print(f'PRONOTEPY: {len(notes_raw)} notes moy={avg}', flush=True)

        # 4. Emploi du temps aujourd'hui
        emploi_du_temps = []
        try:
            today = date.today()
            now   = datetime.now().time()
            lessons = client.lessons(today, today + timedelta(days=1))
            for l in sorted(lessons or [], key=lambda x: x.start):
                en_cours = bool(l.start and l.end and
                                l.start.time() <= now <= l.end.time())
                emploi_du_temps.append({
                    'heure_debut': l.start.strftime('%Hh%M') if l.start else '',
                    'heure_fin':   l.end.strftime('%Hh%M')   if l.end   else '',
                    'matiere':     l.subject.name if l.subject else '',
                    'prof':        l.teacher_name or '',
                    'salle':       l.classroom or '',
                    'annule':      l.canceled or False,
                    'en_cours':    en_cours,
                })
            print(f'PRONOTEPY: {len(emploi_du_temps)} cours', flush=True)
        except Exception as e:
            print(f'EDT_ERROR: {e}', flush=True)

        # 5. Menu cantine
        cantine = []
        try:
            today = date.today()
            menus = client.menus(today, today + timedelta(days=7))
            for menu in (menus or []):
                plats = []
                for cat in [menu.first_meal, menu.main_meal,
                            menu.side_meal, menu.cheese, menu.dessert]:
                    if cat:
                        items = cat if isinstance(cat, list) else [cat]
                        for item in items:
                            if item and hasattr(item,'name') and item.name:
                                plats.append({'plat': item.name, 'bio': False})
                if menu.date:
                    cantine.append({
                        'jour':  menu.date.strftime('%A %-d %B'),
                        'plats': plats,
                    })
            print(f'PRONOTEPY: {len(cantine)} jours cantine', flush=True)
        except Exception as e:
            print(f'CANTINE_ERROR: {e}', flush=True)

        return {
            'notes_recentes':  notes_raw,
            'average':         str(avg),
            'emploi_du_temps': emploi_du_temps,
            'cantine':         cantine,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'error': str(e), 'notes_recentes': [],
                'average': '0', 'emploi_du_temps': [], 'cantine': []}

if __name__ == '__main__':
    result = scrape()
    print(json.dumps(result, ensure_ascii=False))
