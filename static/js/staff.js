/* CampusFix: staff login + staff dashboard */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function slug(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }
  function fmt(iso) {
    var d = new Date(iso);
    return isNaN(d.getTime()) ? '' : d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  }
  function toast(msg, type) {
    var host = $('toast-host');
    if (!host) { host = el('div', 'toast-host'); host.id = 'toast-host'; document.body.appendChild(host); }
    var t = el('div', 'toast toast-' + (type || 'success'), msg);
    host.appendChild(t);
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 3600);
  }
  function busy(btn, on, label, busyLabel) {
    btn.disabled = on;
    btn.innerHTML = '';
    if (on) { btn.appendChild(el('span', 'spinner')); btn.appendChild(document.createTextNode(' ' + busyLabel)); }
    else btn.textContent = label;
  }

  /* =================================================================
     LOGIN PAGE
     ================================================================= */
  var loginForm = $('staff-login-form');
  if (loginForm) {
    var errEl = $('auth-error'), loginBtn = $('auth-btn');
    loginForm.addEventListener('submit', function (e) {
      e.preventDefault();
      errEl.hidden = true;
      var id = $('login_id').value.trim(), pw = $('password').value;
      if (!id || !pw) { errEl.textContent = 'Please enter your staff ID and password.'; errEl.hidden = false; return; }
      busy(loginBtn, true, 'Sign in', 'Signing in\u2026');
      fetch('/api/staff/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ login_id: id, password: pw })
      })
        .then(function (res) { return res.json().catch(function () { return {}; }).then(function (d) { return { ok: res.ok, data: d }; }); })
        .then(function (r) {
          if (r.ok) { window.location.href = '/staff/dashboard'; return; }
          busy(loginBtn, false, 'Sign in');
          errEl.textContent = r.data.error || 'Sign in failed. Please try again.';
          errEl.hidden = false;
        })
        .catch(function () {
          busy(loginBtn, false, 'Sign in');
          errEl.textContent = 'Network error. Please check your connection.';
          errEl.hidden = false;
        });
    });
  }

  /* =================================================================
     DASHBOARD
     ================================================================= */
  if (!$('staff-dashboard')) return;

  var listEl = $('task-list'), loadingEl = $('staff-loading'), emptyEl = $('staff-empty'), errorEl = $('staff-error');
  var state = { tab: 'todo', tickets: [] };
  var MAX_PHOTO = 5 * 1024 * 1024;

  var TABS = {
    todo: {
      filter: function (t) { return t.status === 'Under Review'; },
      empty: ['No tasks to start', 'New assignments from the admin will show up here.']
    },
    progress: {
      filter: function (t) { return t.status === 'In Progress' && !t.after_photo_url; },
      empty: ['Nothing in progress', 'Start a task from the "To start" tab.']
    },
    verify: {
      filter: function (t) { return t.awaiting_verification; },
      empty: ['Nothing waiting', 'Tasks you finish will wait here until the admin verifies them.']
    },
    done: {
      filter: function (t) { return t.status === 'Resolved'; },
      empty: ['No completed tasks yet', 'Verified and resolved tasks will be listed here.']
    }
  };

  function api(url, options) {
    return fetch(url, options).then(function (res) {
      if (res.status === 401) { window.location.href = '/staff/login'; throw new Error('unauthorized'); }
      return res.json().catch(function () { return {}; }).then(function (d) { return { ok: res.ok, data: d }; });
    });
  }

  /* ---------- cards ---------- */
  function beforeThumb(t) {
    if (!t.photo_url) return null;
    var wrap = el('div', 'task-before');
    var link = el('a'); link.href = t.photo_url; link.target = '_blank'; link.rel = 'noopener';
    var img = el('img'); img.src = t.photo_url; img.alt = 'Before photo'; img.loading = 'lazy';
    link.appendChild(img);
    wrap.appendChild(link);
    wrap.appendChild(el('span', 'task-before-label', 'Before'));
    return wrap;
  }

  function startAction(t) {
    var box = el('div', 'task-actions');
    var btn = el('button', 'btn btn-primary', 'Start work');
    btn.type = 'button';
    btn.addEventListener('click', function () {
      busy(btn, true, 'Start work', 'Starting\u2026');
      api('/api/staff/tickets/' + encodeURIComponent(t.ticket_id) + '/start', { method: 'POST' })
        .then(function (r) {
          if (!r.ok) { busy(btn, false, 'Start work'); toast(r.data.error || 'Could not start this task.', 'error'); return; }
          toast(t.ticket_id + ' is now In Progress');
          state.tab = 'progress';
          load();
        })
        .catch(function (err) { if (err.message !== 'unauthorized') { busy(btn, false, 'Start work'); toast('Network error.', 'error'); } });
    });
    box.appendChild(btn);
    return box;
  }

  function completeAction(t) {
    var box = el('div', 'task-actions task-complete');
    box.appendChild(el('div', 'label', 'Upload After photo (proof of the fix)'));

    var file = el('input', 'input');
    file.type = 'file';
    file.accept = 'image/png,image/jpeg';
    file.setAttribute('aria-label', 'After photo for ' + t.ticket_id);
    box.appendChild(file);

    var preview = el('img', 'task-preview');
    preview.alt = 'After photo preview';
    preview.hidden = true;
    box.appendChild(preview);

    var note = el('input', 'input');
    note.type = 'text';
    note.maxLength = 300;
    note.placeholder = 'Optional note (what was fixed)';
    note.style.marginTop = '10px';
    box.appendChild(note);

    var msg = el('div', 'alert alert-error');
    msg.hidden = true;
    msg.style.marginTop = '10px';
    box.appendChild(msg);

    var url = null;
    file.addEventListener('change', function () {
      msg.hidden = true;
      var f = file.files && file.files[0];
      if (url) { URL.revokeObjectURL(url); url = null; }
      if (!f) { preview.hidden = true; return; }
      if (['image/png', 'image/jpeg'].indexOf(f.type) === -1) {
        file.value = ''; preview.hidden = true;
        msg.textContent = 'Photo must be a PNG or JPG image.'; msg.hidden = false; return;
      }
      if (f.size > MAX_PHOTO) {
        file.value = ''; preview.hidden = true;
        msg.textContent = 'Photo is too large (max 5MB).'; msg.hidden = false; return;
      }
      url = URL.createObjectURL(f);
      preview.src = url;
      preview.hidden = false;
    });

    var btn = el('button', 'btn btn-primary btn-block', 'Upload photo & mark complete');
    btn.type = 'button';
    btn.style.marginTop = '12px';
    btn.addEventListener('click', function () {
      msg.hidden = true;
      if (!file.files || !file.files[0]) { msg.textContent = 'Please choose the After photo first.'; msg.hidden = false; return; }
      var fd = new FormData();
      fd.append('after_photo', file.files[0]);
      if (note.value.trim()) fd.append('note', note.value.trim());
      busy(btn, true, 'Upload photo & mark complete', 'Uploading\u2026');
      api('/api/staff/tickets/' + encodeURIComponent(t.ticket_id) + '/complete', { method: 'POST', body: fd })
        .then(function (r) {
          if (!r.ok) {
            busy(btn, false, 'Upload photo & mark complete');
            msg.textContent = r.data.error || 'Upload failed. Please try again.';
            msg.hidden = false;
            return;
          }
          toast(t.ticket_id + ' sent to admin for verification');
          state.tab = 'verify';
          load();
        })
        .catch(function (err) {
          if (err.message === 'unauthorized') return;
          busy(btn, false, 'Upload photo & mark complete');
          msg.textContent = 'Network error. Please try again.';
          msg.hidden = false;
        });
    });
    box.appendChild(btn);
    return box;
  }

  function buildCard(t) {
    var card = el('article', 'card feed-card' + (t.urgency === 'Critical' ? ' is-critical' : ''));

    var top = el('div', 'feed-top');
    top.appendChild(el('div', 'feed-cat', t.category));
    top.appendChild(el('span', 'badge badge-' + slug(t.status), t.status));
    card.appendChild(top);

    var meta = el('div', 'feed-meta');
    meta.appendChild(el('span', 'td-id', t.ticket_id));
    meta.appendChild(el('span', 'muted', 'Wing ' + t.wing + ' \u00b7 Room ' + t.room));
    meta.appendChild(el('span', 'urg-' + slug(t.urgency), t.urgency));
    card.appendChild(meta);

    card.appendChild(el('p', 'task-desc', t.description));

    var compare = window.CFCompare ? window.CFCompare.build(t) : null;
    if (compare) card.appendChild(compare);
    else { var thumb = beforeThumb(t); if (thumb) card.appendChild(thumb); }

    if (t.status === 'Under Review') card.appendChild(startAction(t));
    else if (t.status === 'In Progress' && !t.after_photo_url) card.appendChild(completeAction(t));
    else if (t.awaiting_verification) card.appendChild(el('div', 'alert alert-info task-note', 'Submitted ' + fmt(t.completed_at) + '. Waiting for the admin to verify your proof.'));
    else if (t.status === 'Resolved') card.appendChild(el('div', 'alert alert-success task-note', 'Resolved' + (t.resolved_at ? ' on ' + fmt(t.resolved_at) : '') + '. Good work!'));
    return card;
  }

  /* ---------- rendering ---------- */
  function render() {
    var counts = {};
    Object.keys(TABS).forEach(function (k) { counts[k] = state.tickets.filter(TABS[k].filter).length; });
    $('n-todo').textContent = counts.todo;
    $('n-progress').textContent = counts.progress;
    $('n-verify').textContent = counts.verify;
    $('n-done').textContent = counts.done;
    Array.prototype.forEach.call(document.querySelectorAll('.staff-stats .stat-card'), function (b) {
      b.classList.toggle('active', b.getAttribute('data-tab') === state.tab);
    });

    listEl.innerHTML = '';
    var items = state.tickets.filter(TABS[state.tab].filter);
    if (!items.length) {
      $('staff-empty-title').textContent = TABS[state.tab].empty[0];
      $('staff-empty-text').textContent = TABS[state.tab].empty[1];
      emptyEl.hidden = false;
      return;
    }
    emptyEl.hidden = true;
    items.forEach(function (t) { listEl.appendChild(buildCard(t)); });
  }

  function load() {
    errorEl.hidden = true;
    api('/api/staff/tickets').then(function (r) {
      loadingEl.hidden = true;
      if (!r.ok) { errorEl.textContent = r.data.error || 'Could not load your tasks.'; errorEl.hidden = false; return; }
      var dept = $('staff-dept');
      if (r.data.staff && r.data.staff.department) { dept.textContent = r.data.staff.department; dept.hidden = false; }
      state.tickets = r.data.tickets;
      render();
    }).catch(function (err) {
      loadingEl.hidden = true;
      if (err.message !== 'unauthorized') { errorEl.textContent = 'Network error while loading your tasks.'; errorEl.hidden = false; }
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll('.staff-stats .stat-card'), function (b) {
    b.addEventListener('click', function () { state.tab = b.getAttribute('data-tab'); render(); });
  });

  load();
})();
