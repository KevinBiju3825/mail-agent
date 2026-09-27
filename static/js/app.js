// Shared client-side helpers

// ---- Theme -------------------------------------------------------------
const themeToggle = document.getElementById('themeToggle');
const savedTheme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

if (themeToggle) {
    themeToggle.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('theme', next);
    });
}

// ---- Toasts ------------------------------------------------------------
function toast(message, type = 'info', duration = 3500) {
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = message;
    document.getElementById('toast-container').appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transition = 'opacity .3s ease';
        setTimeout(() => el.remove(), 300);
    }, duration);
}
window.toast = toast;

// ---- API helper --------------------------------------------------------
async function api(url, options = {}) {
    const opts = {
        method: options.method || 'GET',
        headers: { 'Content-Type': 'application/json' },
    };
    if (options.body) opts.body = JSON.stringify(options.body);
    const res = await fetch(url, opts);
    let data = {};
    try { data = await res.json(); } catch (e) { /* not json */ }
    if (!res.ok) {
        const err = data.error || `Request failed (${res.status})`;
        throw new Error(err);
    }
    return data;
}
window.api = api;

// ---- Format helpers ----------------------------------------------------
function fmtDate(iso) {
    if (!iso) return '';
    try {
        const d = new Date(iso);
        const now = new Date();
        const diffMs = now - d;
        const diffMin = Math.floor(diffMs / 60000);
        const diffH = Math.floor(diffMin / 60);
        const diffD = Math.floor(diffH / 24);
        if (diffMin < 1) return 'just now';
        if (diffMin < 60) return `${diffMin}m ago`;
        if (diffH < 24) return `${diffH}h ago`;
        if (diffD < 7) return `${diffD}d ago`;
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    } catch (e) { return iso.substring(0, 10); }
}
window.fmtDate = fmtDate;

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
window.escapeHtml = escapeHtml;

// ---- Modal ------------------------------------------------------------
function showModal({ title, body, footer, onClose }) {
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop';
    backdrop.innerHTML = `
        <div class="modal" role="dialog">
            <div class="modal-header">
                <div class="modal-title">${escapeHtml(title)}</div>
                <button class="modal-close" data-close>&times;</button>
            </div>
            <div class="modal-body"></div>
            ${footer ? '<div class="modal-footer"></div>' : ''}
        </div>
    `;
    const bodyEl = backdrop.querySelector('.modal-body');
    if (typeof body === 'string') bodyEl.innerHTML = body;
    else if (body) bodyEl.appendChild(body);

    if (footer) {
        const footEl = backdrop.querySelector('.modal-footer');
        if (typeof footer === 'string') footEl.innerHTML = footer;
        else footEl.appendChild(footer);
    }

    const close = () => {
        backdrop.remove();
        if (onClose) onClose();
    };
    backdrop.querySelector('[data-close]').addEventListener('click', close);
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) close();
    });
    document.body.appendChild(backdrop);
    return { close, root: backdrop };
}
window.showModal = showModal;

// ---- Global button loading state ---------------------------------------
window.busyBtn = (btn, running = true, label = null) => {
    if (running) {
        btn.dataset.originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner"></span> ${label || 'Working...'}`;
    } else {
        btn.disabled = false;
        if (btn.dataset.originalHtml) btn.innerHTML = btn.dataset.originalHtml;
    }
};

// Auto-dismiss flash messages after 6s
document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .5s'; setTimeout(() => el.remove(), 500); }, 6000);
});
