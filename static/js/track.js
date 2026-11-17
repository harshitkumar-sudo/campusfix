/* CampusFix: track page logic (Part 2) */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var form = $('track-form'), input = $('ticket-input'), btn = $('track-btn');
  var loadingEl = $('track-loading'), errorEl = $('track-error'), notFoundEl = $('not-found'), resultEl = $('result');

  var STEPS = ['Submitted', 'Under Review', 'In Progress', 'Resolved'];

  /* ---------- helpers ---------- */
  function slug(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

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

  function normalizeId(raw) {
    return String(raw || '').trim().replace(/^#/, '').toUpperCase();
  }

  function hideAll() {
    loadingEl.hidden = true;
    errorEl.hidden = true;
    notFoundEl.hidden = true;
    resultEl.hidden = true;
  }

  /* ---------- rendering ---------- */
  function renderStepper(ticket) {
    var host = $('stepper');
    host.innerHTML = '';
    var current = STEPS.indexOf(ticket.status);
    STEPS.forEach(function (name, i) {
      var cls = 'stepper-step';
      var resolved = ticket.status === 'Resolved';
      if (i < current || (resolved && i === current)) cls += ' done';
      else if (i === current) cls += ' current';

      var step = el('div', cls);
      var dot = el('div', 'step-dot', cls.indexOf('done') !== -1 ? '\u2713' : String(i + 1));
      step.appendChild(dot);
      step.appendChild(el('div', 'step-label', name));

      var entry = (ticket.history || []).filter(function (h) { return h.status === name; })[0];
      if (entry) step.appendChild(el('div', 'step-time', fmtShort(entry.timestamp)));
      host.appendChild(step);
    });
  }

  function renderTimeline(ticket) {
    var host = $('timeline');
    host.innerHTML = '';
    var items = (ticket.history || []).slice().reverse(); // newest first
    if (!items.length) {
      host.appendChild(el('li', 'muted', 'No updates yet.'));
      return;
    }
    items.forEach(function (h) {
      var li = el('li');
      var top = el('div', 'tl-top');
      top.appendChild(el('span', 'badge badge-' + slug(h.status), h.status));
      top.appendChild(el('span', 'tl-time', fmt(h.timestamp)));
      li.appendChild(top);
      if (h.note) li.appendChild(el('div', 'tl-note', h.note));
      host.appendChild(li);
    });
  }

  function renderTicket(t) {
    $('r-id').textContent = t.ticket_id;

    var s = $('r-status');
    s.className = 'badge badge-' + slug(t.status);
    s.textContent = t.status;

    var u = $('r-urgency');
    u.className = 'urg-' + slug(t.urgency);
    u.textContent = t.urgency + ' priority';

    $('r-category').textContent = t.category;
    $('r-location').textContent = 'Wing ' + t.wing + ' \u00b7 Room ' + t.room;
    $('r-assigned').textContent = t.assigned_to || 'Not assigned yet';
    $('r-upvotes').textContent = String(t.upvotes || 0);
    $('r-created').textContent = fmt(t.created_at);
    $('r-updated').textContent = fmt(t.updated_at);
    $('r-desc').textContent = t.description;

    var cmp = $('r-compare');
    cmp.innerHTML = '';
    var cmpNode = window.CFCompare ? window.CFCompare.build(t) : null;
    if (cmpNode) { cmp.appendChild(cmpNode); cmp.hidden = false; } else { cmp.hidden = true; }

    var wrap = $('r-photo-wrap');
    if (t.photo_url && !cmpNode) {
      $('r-photo').src = t.photo_url;
      $('r-photo-link').href = t.photo_url;
      wrap.hidden = false;
    } else {
      wrap.hidden = true;
      $('r-photo').removeAttribute('src');
    }

    renderStepper(t);
    renderTimeline(t);
    resultEl.hidden = false;
  }

  /* ---------- lookup ---------- */
  function lookup(id) {
    hideAll();
    btn.disabled = true;
    loadingEl.hidden = false;

    fetch('/api/tickets/' + encodeURIComponent(id))
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          return { status: res.status, ok: res.ok, data: data };
        });
      })
      .then(function (r) {
        loadingEl.hidden = true;
        btn.disabled = false;
        if (r.status === 401) {
          window.location.href = '/login';
        } else if (r.ok) {
          renderTicket(r.data);
        } else if (r.status === 404) {
          notFoundEl.hidden = false;
        } else {
          errorEl.textContent = r.data.error || 'Something went wrong. Please try again.';
          errorEl.hidden = false;
        }
      })
      .catch(function () {
        loadingEl.hidden = true;
        btn.disabled = false;
        errorEl.textContent = 'Network error. Please check your connection and try again.';
        errorEl.hidden = false;
      });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var id = normalizeId(input.value);
    if (!id) {
      hideAll();
      errorEl.textContent = 'Please enter your ticket ID.';
      errorEl.hidden = false;
      input.focus();
      return;
    }
    input.value = id;
    if (window.history && history.replaceState) {
      history.replaceState(null, '', '/track?id=' + encodeURIComponent(id));
    }
    lookup(id);
  });

  /* ---------- auto lookup from ?id= ---------- */
  var params = new URLSearchParams(window.location.search);
  var initial = normalizeId(params.get('id'));
  if (initial) {
    input.value = initial;
    lookup(initial);
  }
})();
