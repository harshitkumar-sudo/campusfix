/* CampusFix: public complaint feed with upvotes (Part 4) */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var listEl = $('feed-list');
  if (!listEl) return;

  var loadingEl = $('feed-loading'), errorEl = $('feed-error'), emptyEl = $('feed-empty');
  var statusSel = $('feed-status'), categorySel = $('feed-category'), tabs = $('feed-tabs');

  var THRESHOLD = 10;
  var IS_STUDENT = (listEl.getAttribute('data-role') === 'student');
  var state = { mode: 'top', status: 'open', category: '' };
  var cards = {};   // ticket_id -> {ticket, node}

  /* ---------- helpers ---------- */
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function slug(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }
  function timeAgo(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    var mins = Math.max(1, Math.round((Date.now() - d.getTime()) / 60000));
    if (mins < 60) return mins + ' min ago';
    var hrs = Math.round(mins / 60);
    if (hrs < 24) return hrs + ' hr ago';
    var days = Math.round(hrs / 24);
    return days + (days === 1 ? ' day ago' : ' days ago');
  }
  function toast(msg, type) {
    var host = $('toast-host');
    if (!host) { host = el('div', 'toast-host'); host.id = 'toast-host'; host.setAttribute('aria-live', 'polite'); document.body.appendChild(host); }
    var t = el('div', 'toast toast-' + (type || 'success'), msg);
    host.appendChild(t);
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 3600);
  }

  /* ---------- card ---------- */
  function buildCard(t) {
    var card = el('article', 'card feed-card' + (t.urgency === 'Critical' ? ' is-critical' : ''));

    var top = el('div', 'feed-top');
    top.appendChild(el('div', 'feed-cat', t.category));
    top.appendChild(el('span', 'badge badge-' + slug(t.status), t.status));
    card.appendChild(top);

    var meta = el('div', 'feed-meta');
    meta.appendChild(el('span', 'muted', 'Wing ' + t.wing + ' \u00b7 Room ' + t.room + ' \u00b7 ' + timeAgo(t.created_at)));
    if (t.urgency === 'Critical') meta.appendChild(el('span', 'urg-critical', 'Critical'));
    if (t.is_mine) meta.appendChild(el('span', 'badge', 'Your complaint'));
    card.appendChild(meta);

    card.appendChild(el('p', 'feed-desc', t.description));

    var compare = window.CFCompare ? window.CFCompare.build(t) : null;
    if (compare) {
      card.appendChild(compare);          // Before | After side by side
    } else if (t.photo_url) {
      var img = el('img', 'feed-photo');
      img.src = t.photo_url;
      img.alt = 'Photo of the reported issue';
      img.loading = 'lazy';
      card.appendChild(img);
    }

    /* progress toward auto-Critical */
    var prog = el('div', 'feed-progress');
    if (t.urgency === 'Critical') {
      prog.appendChild(el('div', 'progress-text critical-text', 'Critical priority'));
    } else {
      var bar = el('div', 'progress-bar');
      var fill = el('div', 'progress-fill');
      fill.style.width = Math.min(100, (t.upvotes / THRESHOLD) * 100) + '%';
      bar.appendChild(fill);
      prog.appendChild(bar);
      prog.appendChild(el('div', 'progress-text', t.upvotes + ' / ' + THRESHOLD + ' upvotes to become Critical'));
    }
    card.appendChild(prog);

    var foot = el('div', 'feed-foot');
    var btn = el('button', 'upvote-btn' + (t.upvoted_by_me ? ' active' : ''));
    btn.type = 'button';
    var arrow = el('span', 'upvote-arrow', '\u25B2');
    arrow.setAttribute('aria-hidden', 'true');
    btn.appendChild(arrow);
    btn.appendChild(el('span', 'upvote-count', String(t.upvotes)));
    var label = t.upvoted_by_me ? 'Upvoted' : 'Upvote';
    btn.appendChild(el('span', 'upvote-label', label));
    btn.setAttribute('aria-pressed', t.upvoted_by_me ? 'true' : 'false');
    btn.setAttribute('aria-label', label + ' ' + t.ticket_id + ' (' + t.upvotes + ' upvotes)');

    if (!IS_STUDENT) {
      btn.disabled = true;
      btn.title = 'Only students can upvote';
    } else if (t.is_mine) {
      btn.disabled = true;
      btn.title = "You can't upvote your own complaint";
    } else if (t.status === 'Resolved') {
      btn.disabled = true;
      btn.title = 'This issue is already resolved';
    } else {
      btn.addEventListener('click', function () { toggleVote(t, btn); });
    }
    foot.appendChild(btn);

    var link = el('a', 'feed-link', t.ticket_id + ' \u2192');
    link.href = '/track?id=' + encodeURIComponent(t.ticket_id);
    foot.appendChild(link);
    card.appendChild(foot);
    return card;
  }

  function replaceCard(t) {
    var entry = cards[t.ticket_id];
    var node = buildCard(t);
    if (entry && entry.node.parentNode) entry.node.parentNode.replaceChild(node, entry.node);
    cards[t.ticket_id] = { ticket: t, node: node };
  }

  /* ---------- voting ---------- */
  function toggleVote(t, btn) {
    btn.disabled = true;
    var method = t.upvoted_by_me ? 'DELETE' : 'POST';
    fetch('/api/tickets/' + encodeURIComponent(t.ticket_id) + '/upvote', { method: method })
      .then(function (res) {
        if (res.status === 401) { window.location.href = '/login'; throw new Error('unauthorized'); }
        return res.json().catch(function () { return {}; }).then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (r) {
        if (!r.ok) {
          btn.disabled = false;
          toast(r.data.error || 'Could not update your vote.', 'error');
          return;
        }
        var updated = Object.assign({}, t, {
          upvotes: r.data.upvotes,
          upvoted_by_me: r.data.upvoted,
          urgency: r.data.urgency
        });
        replaceCard(updated);
        if (r.data.escalated) {
          toast(t.ticket_id + ' reached ' + THRESHOLD + ' upvotes and is now Critical priority!');
        } else if (r.data.upvoted) {
          toast('Upvoted ' + t.ticket_id);
        }
      })
      .catch(function (err) {
        if (err.message === 'unauthorized') return;
        btn.disabled = false;
        toast('Network error. Please try again.', 'error');
      });
  }

  /* ---------- loading ---------- */
  function emptyMessage() {
    if (state.mode === 'mine') return ['You haven\u2019t reported anything yet', 'Spotted a problem on campus? Let the maintenance team know.'];
    if (state.status === 'resolved') return ['No resolved issues yet', 'Resolved issues will show up here.'];
    return ['No issues to show', 'Be the first to report a problem.'];
  }

  function load() {
    errorEl.hidden = true;
    emptyEl.hidden = true;
    listEl.innerHTML = '';
    cards = {};
    loadingEl.hidden = false;

    var params = new URLSearchParams();
    params.set('sort', state.mode === 'top' ? 'top' : 'new');
    params.set('status', state.status);
    if (state.category) params.set('category', state.category);
    if (state.mode === 'mine') params.set('mine', '1');

    fetch('/api/feed?' + params.toString())
      .then(function (res) {
        if (res.status === 401) { window.location.href = '/login'; throw new Error('unauthorized'); }
        if (!res.ok) throw new Error('bad status');
        return res.json();
      })
      .then(function (data) {
        loadingEl.hidden = true;
        THRESHOLD = data.threshold || THRESHOLD;
        if (!data.tickets.length) {
          var m = emptyMessage();
          $('feed-empty-title').textContent = m[0];
          $('feed-empty-text').textContent = m[1];
          emptyEl.hidden = false;
          return;
        }
        data.tickets.forEach(function (t) {
          var node = buildCard(t);
          cards[t.ticket_id] = { ticket: t, node: node };
          listEl.appendChild(node);
        });
      })
      .catch(function (err) {
        if (err.message === 'unauthorized') return;
        loadingEl.hidden = true;
        errorEl.textContent = 'Could not load issues. Please check your connection and refresh.';
        errorEl.hidden = false;
      });
  }

  /* ---------- controls ---------- */
  tabs.addEventListener('click', function (e) {
    var b = e.target.closest('.tab');
    if (!b) return;
    state.mode = b.getAttribute('data-mode');
    Array.prototype.forEach.call(tabs.querySelectorAll('.tab'), function (x) {
      x.classList.toggle('active', x === b);
    });
    if (state.mode === 'mine') { state.status = 'all'; statusSel.value = 'all'; }
    load();
  });
  statusSel.addEventListener('change', function () { state.status = statusSel.value; load(); });
  categorySel.addEventListener('change', function () { state.category = categorySel.value; load(); });

  fetch('/api/meta').then(function (r) { return r.json(); }).then(function (meta) {
    meta.categories.forEach(function (c) {
      var o = el('option', '', c);
      o.value = c;
      categorySel.appendChild(o);
    });
    THRESHOLD = meta.upvote_threshold || THRESHOLD;
  }).catch(function () { /* filter just stays at "All categories" */ });

  load();
})();
