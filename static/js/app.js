// Shared frontend utilities. Loaded by every page via base.html.

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

function showToast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  if (!c) return;
  const colors = {
    info: 'bg-blue-600',
    error: 'bg-rose-600',
    success: 'bg-emerald-600',
  };
  const el = document.createElement('div');
  el.className = `${colors[type] || colors.info} text-white px-4 py-2 rounded-md shadow-lg text-sm transition-opacity duration-300`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.classList.add('opacity-0'), 2200);
  setTimeout(() => el.remove(), 2700);
}

async function api(path, opts = {}) {
  const init = {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  };
  if (init.body && typeof init.body !== 'string') init.body = JSON.stringify(init.body);
  const r = await fetch(path, init);
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      const j = await r.json();
      msg = j.detail || msg;
    } catch (_) { /* ignore */ }
    throw new Error(msg);
  }
  if (r.status === 204) return null;
  return r.json();
}

function renderMarkdown(text) {
  if (window.marked) return marked.parse(text || '');
  return (text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/\n/g, '<br>');
}

function fmtDate(ts) {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleDateString('zh-CN');
}

function fmtDateTime(ts) {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false });
}

function diffBadge(d) {
  const map = {
    easy: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
    medium: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
    hard: 'bg-rose-500/15 text-rose-600 dark:text-rose-400',
  };
  const label = window.LT_I18N
    ? window.LT_I18N.t('diff.' + d, null, d)
    : ({ easy: 'Easy', medium: 'Medium', hard: 'Hard' }[d] || d);
  return `<span class="px-2 py-0.5 rounded text-xs ${map[d] || ''}">${label}</span>`;
}

function t(key, params, fallback) {
  return window.LT_I18N ? window.LT_I18N.t(key, params, fallback) : (fallback || key);
}

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

document.addEventListener('DOMContentLoaded', () => {
  const tt = document.getElementById('theme-toggle');
  if (tt) {
    tt.addEventListener('click', () => {
      const isDark = document.documentElement.classList.toggle('dark');
      localStorage.setItem('theme', isDark ? 'dark' : 'light');
    });
  }
});

window.LT = { api, showToast, renderMarkdown, fmtDate, fmtDateTime, diffBadge, escapeHtml, t };
