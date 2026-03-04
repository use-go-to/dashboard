// chat-notifications.js — Gestion notifications push navigateur
function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

function sendBrowserNotification(title, body) {
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, { body, icon: '/static/icon.png' });
    }
}

// Demander permission au premier clic
document.addEventListener('click', requestNotificationPermission, { once: true });
