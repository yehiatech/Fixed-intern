/* Shared helpers for the dashboard pages (login is stored in localStorage by login.html). */
const API_BASE = window.API_BASE || 'http://localhost:8002';

function getSession() {
    const clean = v => (v && v !== 'null' && v !== 'undefined') ? v : null;
    return {
        role: clean(localStorage.getItem('role')),
        organization_id: clean(localStorage.getItem('organization_id')),
        organization_name: clean(localStorage.getItem('organization_name')),
        user_id: clean(localStorage.getItem('user_id')),
        username: clean(localStorage.getItem('username')),
        full_name: clean(localStorage.getItem('full_name')),
    };
}

/* Returns the session, or sends the visitor to login.html (and returns null). */
function requireSession() {
    const s = getSession();
    if (!s.organization_id || !s.user_id) {
        window.location.href = 'login.html';
        return null;
    }
    return s;
}

/* Escape anything that comes from the database before putting it in innerHTML. */
function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
}

/* JSON fetch helper: throws Error(detail) on non-2xx. */
async function apiFetch(path, options = {}) {
    const init = { method: options.method || 'GET', headers: {} };
    if (options.body !== undefined) {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(options.body);
    }
    const res = await fetch(API_BASE + path, init);
    let data = null;
    try { data = await res.json(); } catch (_) { /* empty body */ }
    if (!res.ok) {
        const detail = data && data.detail;
        throw new Error(typeof detail === 'string' ? detail : ('Request failed (' + res.status + ')'));
    }
    return data;
}

const STATUS_CLASSES = {
    open: 'bg-red-100 text-red-800 border-red-200 focus:ring-red-500',
    in_progress: 'bg-yellow-100 text-yellow-800 border-yellow-200 focus:ring-yellow-500',
    resolved: 'bg-green-100 text-green-800 border-green-200 focus:ring-green-500',
    closed: 'bg-gray-100 text-gray-800 border-gray-200 focus:ring-gray-500',
};

function statusOptionsHtml(current) {
    return [['open', 'Open'], ['in_progress', 'In Progress'], ['resolved', 'Resolved'], ['closed', 'Closed']]
        .map(([v, l]) => `<option class="bg-white text-gray-900" value="${v}" ${v === current ? 'selected' : ''}>${l}</option>`)
        .join('');
}

function formatTicketId(id) { return '#' + id; }
