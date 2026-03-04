// movie-calendar.js
function showMovieCalendarModal(titre, projectionsJson, dureeMinutes) {
    let projections = [];
    try {
        projections = JSON.parse(decodeURIComponent(projectionsJson));
    } catch(e) {
        try { projections = JSON.parse(projectionsJson); } catch(e2) {}
    }

    const modal = document.createElement('div');
    modal.style.cssText = `
        position:fixed;top:0;left:0;width:100vw;height:100vh;
        background:rgba(10,14,26,0.97);z-index:99999;
        display:flex;align-items:center;justify-content:center;
        animation:fadeIn 0.3s ease;
    `;

    let rows = projections.map((p, i) => `
        <tr style="border-bottom:1px solid rgba(74,158,255,0.1);">
            <td style="padding:10px;color:#4a9eff;">${p.cinema}</td>
            <td style="padding:10px;">${p.jour}</td>
            <td style="padding:10px;">
                ${(p.horaires || []).map(h => `
                    <button onclick="addToCalendar('${titre}', '${p.date_iso}', '${h}', ${dureeMinutes}, '${p.cinema}', this)"
                        style="background:rgba(74,158,255,0.2);color:#4a9eff;border:1px solid rgba(74,158,255,0.4);
                               padding:5px 12px;border-radius:8px;margin:2px;cursor:pointer;font-size:13px;
                               transition:all 0.3s;">
                        ${h}
                    </button>
                `).join('')}
            </td>
        </tr>
    `).join('');

    modal.innerHTML = `
        <div style="background:#0d1117;border:1px solid rgba(74,158,255,0.3);border-radius:16px;
                    padding:25px;max-width:600px;width:95%;max-height:80vh;overflow-y:auto;">
            <h2 style="color:#4a9eff;margin-bottom:20px;">📅 ${titre}</h2>
            <p style="opacity:0.7;margin-bottom:20px;font-size:14px;">Choisissez une séance pour l'ajouter à Google Calendar :</p>
            <table style="width:100%;border-collapse:collapse;">${rows}</table>
            <button onclick="this.closest('div').parentElement.remove()"
                style="margin-top:20px;width:100%;background:rgba(255,255,255,0.1);
                       color:white;border:none;padding:12px;border-radius:8px;cursor:pointer;font-size:14px;">
                Fermer
            </button>
        </div>
    `;

    document.body.appendChild(modal);
}

async function addToCalendar(titre, dateIso, horaire, dureeMinutes, cinema, btn) {
    btn.textContent = '⏳';
    btn.disabled = true;
    try {
        const [h, m] = horaire.split(':').map(Number);
        const start = new Date(`${dateIso}T${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:00`);
        const end = new Date(start.getTime() + (dureeMinutes || 120) * 60000);
        const fmt = d => d.toISOString().replace(/[-:]/g,'').split('.')[0]+'Z';
        const gcalUrl = `https://calendar.google.com/calendar/render?action=TEMPLATE`
            + `&text=${encodeURIComponent('🎬 ' + titre)}`
            + `&dates=${fmt(start)}/${fmt(end)}`
            + `&details=${encodeURIComponent('Cinéma : ' + cinema)}`
            + `&location=${encodeURIComponent(cinema)}`;
        window.open(gcalUrl, '_blank');
        btn.textContent = '✅';
    } catch(e) {
        btn.textContent = '❌';
        console.error(e);
    }
}
