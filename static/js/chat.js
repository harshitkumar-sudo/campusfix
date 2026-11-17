/* CampusFix: real-time community chat widget (polling) */
(function () {
  'use strict';

  var root = document.getElementById('chat-root');
  if (!root) return;

  var $ = function (id) { return document.getElementById(id); };
  var launch = $('chat-launch'), panel = $('chat-panel'), closeBtn = $('chat-close');
  var listEl = $('chat-list'), form = $('chat-form'), input = $('chat-input'), sendBtn = $('chat-send');
  var noticeEl = $('chat-notice'), unreadEl = $('chat-unread'), pauseBtn = $('chat-pause'), subEl = $('chat-sub');
  var ROLE = root.getAttribute('data-role');

  var OPEN_MS = 2500, CLOSED_MS = 10000;
  var state = { open: false, lastId: 0, unread: 0, loaded: false, paused: false, canPost: true, timer: null, busy: false };

  /* ---------- helpers ---------- */
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function timeOf(iso) {
    var d = new Date(iso);
    return isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  function dateOf(iso) {
    var d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  }
  function toast(msg, type) {
    var host = $('toast-host');
    if (!host) { host = el('div', 'toast-host'); host.id = 'toast-host'; host.setAttribute('aria-live', 'polite'); document.body.appendChild(host); }
    var t = el('div', 'toast toast-' + (type || 'success'), msg);
    host.appendChild(t);
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 3600);
  }
  function nearBottom() { return listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight < 90; }
  function toBottom() { listEl.scrollTop = listEl.scrollHeight; }

  /* ---------- rendering ---------- */
  function renderMessage(m) {
    var cls = 'chat-msg role-' + m.role + (m.mine ? ' mine' : '');
    var box = el('div', cls);
    var head = el('div', 'chat-msg-head');
    if (m.role === 'admin') head.appendChild(el('span', 'chat-badge chat-badge-admin', '[ADMIN]'));
    if (m.role === 'staff') head.appendChild(el('span', 'chat-badge chat-badge-staff', '[STAFF]'));
    head.appendChild(el('span', 'chat-name', m.mine ? 'You' : m.name));
    head.appendChild(el('span', 'chat-time', timeOf(m.created_at)));
    if (ROLE === 'admin' && m.role === 'student' && m.student_id) {
      var ban = el('button', 'chat-ban', 'Ban');
      ban.type = 'button';
      ban.title = 'Ban ' + m.name + ' from chat';
      ban.addEventListener('click', function () { banStudent(m); });
      head.appendChild(ban);
    }
    box.appendChild(head);
    box.appendChild(el('div', 'chat-text', m.text));
    return box;
  }

  function applyState(data) {
    state.paused = !!data.paused;
    state.canPost = !!data.can_post;

    var notice = '';
    if (data.banned_until) notice = 'You are banned from chat until ' + dateOf(data.banned_until) + '.';
    else if (state.paused && ROLE === 'admin') notice = 'Chat is paused. Only admins can send messages right now.';
    else if (state.paused) notice = 'Chat is currently paused by Admin.';
    noticeEl.textContent = notice;
    noticeEl.hidden = !notice;
    noticeEl.classList.toggle('chat-notice-paused', state.paused);

    input.disabled = !state.canPost;
    sendBtn.disabled = !state.canPost;
    input.placeholder = state.canPost ? 'Type a message\u2026'
      : (data.banned_until ? 'You cannot send messages right now' : 'Chat is paused');
    if (pauseBtn) {
      pauseBtn.textContent = state.paused ? 'Resume chat' : 'Pause chat';
      pauseBtn.classList.toggle('active', state.paused);
    }
    subEl.textContent = state.paused ? 'Paused by Admin' : 'Students, staff and admins';
  }

  /* ---------- polling ---------- */
  function schedule(ms) {
    clearTimeout(state.timer);
    state.timer = setTimeout(tick, ms);
  }
  function interval() { return state.open ? OPEN_MS : CLOSED_MS; }

  function tick() {
    if (document.hidden) { schedule(5000); return; }
    poll().then(function () { schedule(interval()); });
  }

  function poll() {
    if (state.busy) return Promise.resolve();
    state.busy = true;
    return fetch('/api/chat/messages?after=' + state.lastId)
      .then(function (res) {
        if (res.status === 401) { throw new Error('signed-out'); }
        if (!res.ok) throw new Error('bad status');
        return res.json();
      })
      .then(function (data) {
        state.busy = false;
        var first = !state.loaded;
        if (first) listEl.innerHTML = '';
        var stick = first || nearBottom();
        var added = 0, fromOthers = 0;
        data.messages.forEach(function (m) {
          if (m.id <= state.lastId) return;
          listEl.appendChild(renderMessage(m));
          state.lastId = m.id;
          added++;
          if (!m.mine) fromOthers++;
        });
        if (first && !data.messages.length) {
          listEl.appendChild(el('div', 'chat-empty', 'No messages yet. Say hello!'));
        } else if (added) {
          var empty = listEl.querySelector('.chat-empty');
          if (empty) empty.remove();
        }
        state.loaded = true;
        applyState(data);
        if (stick && added) toBottom();
        if (!state.open && !first && fromOthers) {
          state.unread += fromOthers;
          unreadEl.textContent = state.unread > 9 ? '9+' : String(state.unread);
          unreadEl.hidden = false;
        }
      })
      .catch(function (err) {
        state.busy = false;
        if (err.message === 'signed-out') { clearTimeout(state.timer); state.timer = null; throw err; }
        /* network hiccup: just try again on the next tick */
      })
      .catch(function () { /* signed out: stop polling */ });
  }

  /* ---------- sending ---------- */
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || !state.canPost) return;
    sendBtn.disabled = true;
    fetch('/api/chat/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text })
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) { return { ok: res.ok, data: data }; });
      })
      .then(function (r) {
        sendBtn.disabled = !state.canPost;
        if (!r.ok) {
          toast(r.data.error || 'Message not sent.', 'error');
          poll();
          return;
        }
        input.value = '';
        input.focus();
        poll().then(toBottom);
      })
      .catch(function () {
        sendBtn.disabled = !state.canPost;
        toast('Network error. Message not sent.', 'error');
      });
  });

  /* ---------- admin moderation ---------- */
  if (pauseBtn) {
    pauseBtn.addEventListener('click', function () {
      pauseBtn.disabled = true;
      fetch('/api/admin/chat/pause', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paused: !state.paused })
      })
        .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, data: d }; }); })
        .then(function (r) {
          pauseBtn.disabled = false;
          if (!r.ok) { toast(r.data.error || 'Could not change chat state.', 'error'); return; }
          toast(r.data.paused ? 'Chat paused for students and staff' : 'Chat resumed');
          poll();
        })
        .catch(function () { pauseBtn.disabled = false; toast('Network error.', 'error'); });
    });
  }

  function banStudent(m) {
    var answer = window.prompt('Ban ' + m.name + ' from chat for how many days?', '1');
    if (answer === null) return;
    var days = parseInt(answer, 10);
    if (!days || days < 1 || days > 365) { toast('Enter a number of days from 1 to 365.', 'error'); return; }
    fetch('/api/admin/chat/ban', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ student_id: m.student_id, days: days })
    })
      .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, data: d }; }); })
      .then(function (r) {
        if (!r.ok) { toast(r.data.error || 'Could not ban this student.', 'error'); return; }
        toast(m.name + ' is banned from chat for ' + days + (days === 1 ? ' day' : ' days'));
      })
      .catch(function () { toast('Network error.', 'error'); });
  }

  /* ---------- open / close ---------- */
  function setOpen(open) {
    state.open = open;
    panel.hidden = !open;
    launch.setAttribute('aria-expanded', open ? 'true' : 'false');
    launch.classList.toggle('is-open', open);
    if (open) {
      state.unread = 0;
      unreadEl.hidden = true;
      toBottom();
      if (!input.disabled) input.focus();
      poll();
    }
    schedule(interval());
  }
  launch.addEventListener('click', function () { setOpen(!state.open); });
  closeBtn.addEventListener('click', function () { setOpen(false); launch.focus(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && state.open) setOpen(false); });
  document.addEventListener('visibilitychange', function () { if (!document.hidden) { poll(); schedule(interval()); } });

  tick();
})();
