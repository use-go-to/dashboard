# 🏠 Dashboard IoT - Guide de déploiement Render

## Structure du projet
```
dashboard/
├── app.py                  ← Serveur Flask principal
├── requirements.txt        ← Dépendances Python
├── Procfile               ← Commande de démarrage
├── render.yaml            ← Config Render
├── .gitignore
├── templates/
│   └── index.html         ← Interface du dashboard
└── static/
    ├── movie-calendar.js
    ├── chat-notifications.js
    └── sounds.js
```

---

## 🚀 Déploiement en 5 étapes

### 1. Créer le repository GitHub
```bash
cd dashboard
git init
git add .
git commit -m "Initial commit - Dashboard IoT"
```
Puis créer un repo sur github.com et suivre les instructions "push existing repo".

### 2. Créer le service sur Render
- Aller sur https://render.com → New → Web Service
- Connecter votre compte GitHub
- Sélectionner le repository "dashboard"
- Render détecte automatiquement le `render.yaml`

### 3. Variables d'environnement (dans Render Dashboard)
| Variable | Valeur |
|---|---|
| `PRONOTE_USER` | `d.lecointre10` |
| `PRONOTE_PASS` | `David@35160` |
| `WEBHOOK_SECRET` | Votre secret pour les SMS |
| `PERPLEXITY_API_KEY` | *(optionnel)* Votre clé API |

### 4. Build command (Render le fait automatiquement)
```
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install-deps chromium
```

### 5. Start command
```
gunicorn --worker-class gevent -w 1 --bind 0.0.0.0:$PORT --timeout 120 app:app
```

---

## 📱 Recevoir les SMS de votre femme en temps réel

Installer **MacroDroid** ou **Tasker** sur son téléphone Android, puis créer une règle :

**Déclencheur :** SMS reçu (de n'importe qui)
**Action :** Requête HTTP POST
```
URL : https://VOTRE-APP.onrender.com/webhook/sms
Headers : Content-Type: application/json
Body :
{
  "sender": "Femme 💕",
  "message": "%sms_body",
  "secret": "VOTRE_WEBHOOK_SECRET"
}
```

---

## 🔑 Google Calendar (optionnel)
1. Aller sur https://console.cloud.google.com
2. Créer un projet → APIs → Google Calendar API → Activer
3. Credentials → OAuth 2.0 → Application de bureau
4. Télécharger `credentials.json` et l'uploader sur le serveur

---

## ⚠️ Notes importantes
- **Render plan gratuit** : le serveur se met en veille après 15 min d'inactivité
- Pour éviter la veille : utiliser **UptimeRobot** (gratuit) qui ping votre URL toutes les 5 min
- Les SMS sont stockés **en mémoire** → effacés à chaque redémarrage (comportement normal)
- Pronote se scrape toutes les 30 min (mise en cache)
