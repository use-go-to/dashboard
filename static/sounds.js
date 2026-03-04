// sounds.js — Système de sons pour notifications
const soundSystem = {
    _initialized: false,
    _ctx: null,

    init() {
        if (this._initialized) return;
        try {
            this._ctx = new (window.AudioContext || window.webkitAudioContext)();
            this._initialized = true;
        } catch(e) {}
    },

    playNotification() {
        if (!this._initialized || !this._ctx) return;
        try {
            const osc = this._ctx.createOscillator();
            const gain = this._ctx.createGain();
            osc.connect(gain);
            gain.connect(this._ctx.destination);

            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, this._ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(440, this._ctx.currentTime + 0.3);

            gain.gain.setValueAtTime(0.3, this._ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, this._ctx.currentTime + 0.4);

            osc.start(this._ctx.currentTime);
            osc.stop(this._ctx.currentTime + 0.4);
        } catch(e) {}
    },

    playAlert() {
        if (!this._initialized || !this._ctx) return;
        for (let i = 0; i < 3; i++) {
            setTimeout(() => {
                try {
                    const osc = this._ctx.createOscillator();
                    const gain = this._ctx.createGain();
                    osc.connect(gain);
                    gain.connect(this._ctx.destination);
                    osc.type = 'square';
                    osc.frequency.value = 800;
                    gain.gain.setValueAtTime(0.5, this._ctx.currentTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, this._ctx.currentTime + 0.3);
                    osc.start(this._ctx.currentTime);
                    osc.stop(this._ctx.currentTime + 0.3);
                } catch(e) {}
            }, i * 400);
        }
    }
};
