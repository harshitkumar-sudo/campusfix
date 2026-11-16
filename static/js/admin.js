/* CampusFix: admin login + dashboard logic (Part 3) */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  /* ---------- shared helpers ---------- */
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function slug(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }
  function fmt(iso) {
    if (!iso) return '\u2014';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  function fmtShort(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  }
  function fillSelect(sel, items, placeholder) {
    sel.innerHTML = '';
    if (placeholder !== null && placeholder !== undefined) {
      var first = el('option', '', placeholder);
      first.value = '';
      sel.appendChild(first);
    }
    items.forEach(function (item) {
      var o = el('option', '', item);
      o.value = item;
      sel.appendChild(o);
    });
  }

  /* Fetch wrapper: returns {ok,status,data}. Redirects to login on 401 unless noRedirect. */
  function api(url, options, noRedirect) {
    options = options || {};
    options.credentials = 'same-origin';
    return fetch(url, options).then(function (res) {
      if (res.status === 401 && !noRedirect) {
        window.location.href = '/admin/login';
        throw new Error('unauthorized');
      }
      return res.json().catch(function () { return {}; }).then(function (data) {
        return { ok: res.ok, status: res.status, data: data };
      });
    });
  }
  function jsonBody(method, body) {
    return { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  }

  /* =====================================================================
     LOGIN PAGE
     ===================================================================== */
  var loginForm = $('login-form');
  if (loginForm) {
    var loginErr = $('login-error'), loginBtn = $('login-btn');
    loginForm.addEventListener('submit', function (e) {
      e.preventDefault();
      loginErr.hidden = true;
      var username = $('username').value.trim();
      var password = $('password').value;
      if (!username || !password) {
        loginErr.textContent = 'Please enter your username and password.';
        loginErr.hidden = false;
        return;
      }
      loginBtn.disabled = true;
      loginBtn.innerHTML = '';
      loginBtn.appendChild(el('span', 'spinner'));
      loginBtn.appendChild(document.createTextNode(' Signing in\u2026'));

      api('/api/admin/login', jsonBody('POST', { username: username, password: password }), true)
        .then(function (r) {
          if (r.ok) { window.location.href = '/admin'; return; }
          throw new Error(r.data.error || 'Sign in failed. Please try again.');
        })
        .catch(function (err) {
          loginBtn.disabled = false;
          loginBtn.textContent = 'Sign in';
          loginErr.textContent = err.message === 'Failed to fetch'
            ? 'Network error. Please check your connection.' : err.message;
          loginErr.hidden = false;
        });
    });
  }

  /* =====================================================================
     DASHBOARD PAGE
     ===================================================================== */
  if ($('dashboard')) initDashboard();

  function initDashboard() {
    var state = {
      meta: null,
      filters: { q: '', status: '', urgency: '', category: '' },
      current: null,       // ticket open in drawer
      lastFocus: null
    };

    var fQ = $('f-q'), fStatus = $('f-status'), fUrgency = $('f-urgency'), fCategory = $('f-category');
    var critBtn = $('crit-btn'), clearBtn = $('clear-btn');
    var tbody = $('tickets-body'), tableCard = $('table-card'), emptyEl = $('tickets-empty');
    var loadingEl = $('tickets-loading'), countEl = $('list-count'), dashErr = $('dash-error');
    var drawer = $('drawer'), overlay = $('drawer-overlay');

    /* ---------- toast ---------- */
    function toast(msg, type) {
      var t = el('div', 'toast toast-' + (type || 'success'), msg);
      $('toast-host').appendChild(t);
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 3200);
    }
    function showDashError(msg) { dashErr.textContent = msg; dashErr.hidden = false; }

    /* ---------- stats ---------- */
    function renderStats(s) {
      $('st-total').textContent = s.total;
      $('st-pending').textContent = s.pending;
      $('st-submitted').textContent = s.by_status['Submitted'] || 0;
      $('st-review').textContent = s.by_status['Under Review'] || 0;
      $('st-progress').textContent = s.by_status['In Progress'] || 0;
      $('st-resolved').textContent = s.by_status['Resolved'] || 0;

      var bars = $('cat-bars');
      bars.innerHTML = '';
      var cats = Object.keys(s.by_category);
      var max = Math.max.apply(null, cats.map(function (c) { return s.by_category[c]; }).concat([1]));
      cats.forEach(function (c) {
        var row = el('div', 'bar-row');
        row.appendChild(el('div', 'bar-label', c));
        var track = el('div', 'bar-track');
        var fill = el('div', 'bar-fill');
        fill.style.width = (s.by_category[c] / max * 100) + '%';
        track.appendChild(fill);
        row.appendChild(track);
        row.appendChild(el('div', 'bar-count', String(s.by_category[c])));
        bars.appendChild(row);
      });

      var urg = $('urg-summary');
      urg.innerHTML = '';
      ['Critical', 'Medium', 'Low'].forEach(function (u) {
        urg.appendChild(el('span', 'urg-' + slug(u), u + ': ' + (s.by_urgency[u] || 0)));
      });

      var hs = $('hotspots');
      hs.innerHTML = '';
      if (!s.hotspots.length) {
        hs.appendChild(el('li', 'muted', 'No data yet.'));
      }
      s.hotspots.forEach(function (h) {
        var li = el('li', h.count >= 2 ? 'recurring' : '');
        li.appendChild(el('span', 'hs-loc', 'Wing ' + h.wing + ' \u00b7 Room ' + h.room));
        li.appendChild(el('span', 'hs-count', h.count + (h.count === 1 ? ' report' : ' reports')));
        hs.appendChild(li);
      });

      document.querySelectorAll('button.stat-card').forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-status') === state.filters.status);
      });
    }

    function loadStats() {
      return api('/api/admin/stats').then(function (r) {
        if (r.ok) renderStats(r.data);
      }).catch(function (err) { if (err.message !== 'unauthorized') showDashError('Could not load statistics.'); });
    }

    /* ---------- tickets table ---------- */
    function td(label, cls) {
      var c = el('td', cls || '');
      c.setAttribute('data-label', label);
      return c;
    }

    function renderTickets(list) {
      tbody.innerHTML = '';
      countEl.textContent = list.length + (list.length === 1 ? ' ticket' : ' tickets') + ' found';
      if (!list.length) {
        tableCard.hidden = true;
        emptyEl.hidden = false;
        return;
      }
      emptyEl.hidden = true;
      tableCard.hidden = false;

      list.forEach(function (t) {
        var tr = el('tr');
        tr.tabIndex = 0;

        var c = td('Ticket', 'td-id'); c.textContent = t.ticket_id; tr.appendChild(c);
        c = td('Category'); c.textContent = t.category; tr.appendChild(c);
        c = td('Location', 'td-nowrap'); c.textContent = 'Wing ' + t.wing + ' \u00b7 ' + t.room; tr.appendChild(c);
        c = td('Issue', 'td-desc'); c.appendChild(el('span', '', t.description)); tr.appendChild(c);
        c = td('Urgency'); c.appendChild(el('span', 'urg-' + slug(t.urgency), t.urgency)); tr.appendChild(c);

        c = td('Votes'); c.textContent = String(t.upvotes || 0); tr.appendChild(c);

        c = td('Status');
        var sel = el('select', 'input status-select');
        sel.setAttribute('aria-label', 'Change status of ' + t.ticket_id);
        fillSelect(sel, state.meta.statuses, null);
        sel.value = t.status;
        sel.addEventListener('click', function (e) { e.stopPropagation(); });
        sel.addEventListener('keydown', function (e) { e.stopPropagation(); });
        sel.addEventListener('change', function () { quickStatus(t, sel); });
        c.appendChild(sel);
        tr.appendChild(c);

        c = td('Assigned to', t.assigned_to ? '' : 'td-muted'); c.textContent = t.assigned_to || 'Unassigned'; tr.appendChild(c);
        c = td('Updated', 'td-nowrap td-muted'); c.textContent = fmt(t.updated_at); tr.appendChild(c);

        tr.addEventListener('click', function () { openDrawer(t.ticket_id); });
        tr.addEventListener('keydown', function (e) {
          if (e.target === tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openDrawer(t.ticket_id); }
        });
        tbody.appendChild(tr);
      });
    }

    function loadTickets() {
      var params = new URLSearchParams();
      Object.keys(state.filters).forEach(function (k) {
        if (state.filters[k]) params.set(k, state.filters[k]);
      });
      loadingEl.hidden = false;
      tableCard.hidden = true;
      emptyEl.hidden = true;
      return api('/api/admin/tickets?' + params.toString()).then(function (r) {
        loadingEl.hidden = true;
        if (!r.ok) { showDashError(r.data.error || 'Could not load tickets.'); return; }
        dashErr.hidden = true;
        renderTickets(r.data.tickets);
      }).catch(function (err) {
        loadingEl.hidden = true;
        if (err.message !== 'unauthorized') showDashError('Network error while loading tickets.');
      });
    }

    function refreshAll() { return Promise.all([loadTickets(), loadStats()]); }

    /* One-click status change straight from the table */
    function quickStatus(ticket, sel) {
      var newStatus = sel.value;
      sel.disabled = true;
      api('/api/admin/tickets/' + encodeURIComponent(ticket.ticket_id),
          jsonBody('PATCH', { status: newStatus }))
        .then(function (r) {
          if (!r.ok) {
            sel.value = ticket.status;
            toast(r.data.error || 'Could not update status.', 'error');
            sel.disabled = false;
            return;
          }
          toast(ticket.ticket_id + ' moved to ' + newStatus);
          if (state.current && state.current.ticket_id === ticket.ticket_id) renderDrawer(r.data);
          refreshAll();
        })
        .catch(function (err) {
          sel.value = ticket.status;
          sel.disabled = false;
          if (err.message !== 'unauthorized') toast('Network error. Status not changed.', 'error');
        });
    }

    /* ---------- filters ---------- */
    function syncFilterUI() {
      fQ.value = state.filters.q;
      fStatus.value = state.filters.status;
      fUrgency.value = state.filters.urgency;
      fCategory.value = state.filters.category;
      critBtn.classList.toggle('active', state.filters.urgency === 'Critical');
      document.querySelectorAll('button.stat-card').forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-status') === state.filters.status);
      });
    }
    function applyFilters() { syncFilterUI(); loadTickets(); }

    var searchTimer = null;
    fQ.addEventListener('input', function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        state.filters.q = fQ.value.trim();
        applyFilters();
      }, 300);
    });
    fStatus.addEventListener('change', function () { state.filters.status = fStatus.value; applyFilters(); });
    fUrgency.addEventListener('change', function () { state.filters.urgency = fUrgency.value; applyFilters(); });
    fCategory.addEventListener('change', function () { state.filters.category = fCategory.value; applyFilters(); });
    critBtn.addEventListener('click', function () {
      state.filters.urgency = state.filters.urgency === 'Critical' ? '' : 'Critical';
      applyFilters();
    });
    clearBtn.addEventListener('click', function () {
      state.filters = { q: '', status: '', urgency: '', category: '' };
      applyFilters();
    });
    document.querySelectorAll('button.stat-card').forEach(function (b) {
      b.addEventListener('click', function () {
        state.filters.status = b.getAttribute('data-status') || '';
        applyFilters();
      });
    });

    $('refresh-btn').addEventListener('click', function () { refreshAll(); toast('Refreshed'); });
    $('logout-btn').addEventListener('click', function () {
      api('/api/admin/logout', { method: 'POST' }, true)
        .then(function () { window.location.href = '/admin/login'; })
        .catch(function () { window.location.href = '/admin/login'; });
    });

    /* ---------- drawer ---------- */
    var dMsg = $('d-msg'), dSave = $('d-save');

    function showDrawerMsg(text, type) {
      dMsg.className = 'alert alert-' + type;
      dMsg.textContent = text;
      dMsg.hidden = false;
    }

    function renderDrawer(t) {
      state.current = t;
      $('d-id').textContent = t.ticket_id;

      var sb = $('d-status-badge');
      sb.className = 'badge badge-' + slug(t.status);
      sb.textContent = t.status;
      var ub = $('d-urgency-badge');
      ub.className = 'urg-' + slug(t.urgency);
      ub.textContent = t.urgency + ' priority';

      $('d-category').textContent = t.category;
      $('d-reporter').textContent = t.reporter ? t.reporter.name + ' (' + t.reporter.roll_no + ')' : 'Unknown';
      $('d-upvotes').textContent = String(t.upvotes || 0);
      $('d-location').textContent = 'Wing ' + t.wing + ' \u00b7 Room ' + t.room;
      $('d-created').textContent = fmt(t.created_at);
      $('d-updated').textContent = fmt(t.updated_at);
      $('d-desc').textContent = t.description;

      var wrap = $('d-photo-wrap');
      if (t.photo_url) {
        $('d-photo').src = t.photo_url;
        $('d-photo-link').href = t.photo_url;
        wrap.hidden = false;
      } else {
        wrap.hidden = true;
        $('d-photo').removeAttribute('src');
      }

      $('d-status').value = t.status;
      $('d-urgency').value = t.urgency;
      $('d-assigned').value = t.assigned_to || '';
      $('d-note').value = '';

      var hist = $('d-history');
      hist.innerHTML = '';
      var items = (t.history || []).slice().reverse();
      if (!items.length) hist.appendChild(el('li', 'muted', 'No history yet.'));
      items.forEach(function (h) {
        var li = el('li');
        var top = el('div', 'tl-top');
        top.appendChild(el('span', 'badge badge-' + slug(h.status), h.status));
        top.appendChild(el('span', 'tl-time', fmt(h.timestamp)));
        li.appendChild(top);
        if (h.note) li.appendChild(el('div', 'tl-note', h.note));
        hist.appendChild(li);
      });
    }

    function openDrawer(ticketId) {
      state.lastFocus = document.activeElement;
      dMsg.hidden = true;
      $('d-content').hidden = true;
      $('d-loading').hidden = false;
      $('d-id').textContent = ticketId;
      overlay.hidden = false;
      drawer.classList.add('open');
      drawer.setAttribute('aria-hidden', 'false');
      document.body.style.overflow = 'hidden';
      $('drawer-close').focus();

      api('/api/tickets/' + encodeURIComponent(ticketId)).then(function (r) {
        $('d-loading').hidden = true;
        if (!r.ok) { showDrawerMsg(r.data.error || 'Could not load ticket.', 'error'); $('d-content').hidden = false; return; }
        renderDrawer(r.data);
        $('d-content').hidden = false;
      }).catch(function (err) {
        $('d-loading').hidden = true;
        if (err.message !== 'unauthorized') { $('d-content').hidden = false; showDrawerMsg('Network error while loading ticket.', 'error'); }
      });
    }

    function closeDrawer() {
      drawer.classList.remove('open');
      drawer.setAttribute('aria-hidden', 'true');
      overlay.hidden = true;
      document.body.style.overflow = '';
      state.current = null;
      if (state.lastFocus && state.lastFocus.focus) state.lastFocus.focus();
    }
    $('drawer-close').addEventListener('click', closeDrawer);
    overlay.addEventListener('click', closeDrawer);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && drawer.classList.contains('open')) closeDrawer();
    });

    dSave.addEventListener('click', function () {
      var t = state.current;
      if (!t) return;
      dMsg.hidden = true;

      var body = {};
      var status = $('d-status').value, urgency = $('d-urgency').value, assigned = $('d-assigned').value;
      var note = $('d-note').value.trim();
      if (status !== t.status) body.status = status;
      if (urgency !== t.urgency) body.urgency = urgency;
      if (assigned !== (t.assigned_to || '')) body.assigned_to = assigned;
      if (note) body.note = note;
      if (!Object.keys(body).length) { showDrawerMsg('No changes to save.', 'info'); return; }

      dSave.disabled = true;
      dSave.innerHTML = '';
      dSave.appendChild(el('span', 'spinner'));
      dSave.appendChild(document.createTextNode(' Saving\u2026'));

      api('/api/admin/tickets/' + encodeURIComponent(t.ticket_id), jsonBody('PATCH', body))
        .then(function (r) {
          dSave.disabled = false;
          dSave.textContent = 'Save changes';
          if (!r.ok) { showDrawerMsg(r.data.error || 'Could not save changes.', 'error'); return; }
          renderDrawer(r.data);
          showDrawerMsg('Changes saved.', 'success');
          toast(r.data.ticket_id + ' updated');
          refreshAll();
        })
        .catch(function (err) {
          dSave.disabled = false;
          dSave.textContent = 'Save changes';
          if (err.message !== 'unauthorized') showDrawerMsg('Network error. Changes were not saved.', 'error');
        });
    });

    /* ---------- boot ---------- */
    api('/api/meta').then(function (r) {
      if (!r.ok) throw new Error('meta');
      state.meta = r.data;
      fillSelect(fStatus, state.meta.statuses, 'All statuses');
      fillSelect(fUrgency, state.meta.urgencies, 'All urgencies');
      fillSelect(fCategory, state.meta.categories, 'All categories');
      fillSelect($('d-status'), state.meta.statuses, null);
      fillSelect($('d-urgency'), state.meta.urgencies, null);
      var assigned = $('d-assigned');
      fillSelect(assigned, state.meta.staff, 'Unassigned');
      return refreshAll();
    }).catch(function (err) {
      loadingEl.hidden = true;
      if (err.message !== 'unauthorized') showDashError('Could not load dashboard data. Please refresh the page.');
    });
  }
})();
