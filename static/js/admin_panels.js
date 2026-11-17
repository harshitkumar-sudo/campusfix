/* CampusFix admin: tabs, resolution verification, staff management, chat moderation */
(function () {
  'use strict';

  var A = window.CFAdmin;
  if (!A || !document.getElementById('dashboard')) return;

  var $ = function (id) { return document.getElementById(id); };
  var el = A.el, api = A.api, toast = A.toast, fmt = A.fmt, jsonBody = A.jsonBody;

  /* ---------- tabs ---------- */
  var loaded = { verify: false, staff: false, chat: false };
  var current = 'tickets';

  function showTab(name) {
    current = name;
    Array.prototype.forEach.call(document.querySelectorAll('#admin-tabs .tab'), function (b) {
      b.classList.toggle('active', b.getAttribute('data-tab') === name);
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-panel]'), function (p) {
      p.hidden = p.getAttribute('data-panel') !== name;
    });
    if (name === 'verify') loadVerification();
    if (name === 'staff') loadStaff();
    if (name === 'chat') loadModeration();
  }
  $('admin-tabs').addEventListener('click', function (e) {
    var b = e.target.closest('.tab');
    if (b) showTab(b.getAttribute('data-tab'));
  });
  $('refresh-btn').addEventListener('click', function () {
    if (current === 'verify') loadVerification();
    if (current === 'staff') loadStaff();
    if (current === 'chat') loadModeration();
  });

  /* =================================================================
     Verification
     ================================================================= */
  function verifyCard(t) {
    var card = el('article', 'card verify-card');

    var head = el('div', 'feed-top');
    var title = el('div');
    title.appendChild(el('span', 'td-id', t.ticket_id));
    title.appendChild(el('span', 'muted', '  \u00b7  ' + t.category));
    head.appendChild(title);
    head.appendChild(el('span', 'urg-' + A.slug(t.urgency), t.urgency));
    card.appendChild(head);

    var meta = el('div', 'verify-meta muted');
    meta.textContent = 'Wing ' + t.wing + ' \u00b7 Room ' + t.room +
      '  |  Staff: ' + (t.assigned_to || 'Unassigned') +
      '  |  Proof uploaded ' + fmt(t.completed_at) +
      (t.reporter ? '  |  Reported by ' + t.reporter.name : '');
    card.appendChild(meta);

    card.appendChild(el('p', 'task-desc', t.description));
    var cmp = window.CFCompare.build(t);
    if (cmp) card.appendChild(cmp);

    var note = el('input', 'input');
    note.type = 'text';
    note.maxLength = 300;
    note.placeholder = 'Optional note for the history (required reason helps staff when sending back)';
    note.style.marginTop = '12px';
    card.appendChild(note);

    var actions = el('div', 'verify-actions');
    var approve = el('button', 'btn btn-primary', 'Approve & mark Resolved');
    var reject = el('button', 'btn btn-danger', 'Send back to staff');
    var details = el('button', 'btn', 'Details');
    [approve, reject, details].forEach(function (b) { b.type = 'button'; actions.appendChild(b); });
    card.appendChild(actions);

    function act(action) {
      approve.disabled = reject.disabled = true;
      api('/api/admin/tickets/' + encodeURIComponent(t.ticket_id) + '/verify',
          jsonBody('POST', { action: action, note: note.value.trim() }))
        .then(function (r) {
          if (!r.ok) {
            approve.disabled = reject.disabled = false;
            toast(r.data.error || 'Could not update this ticket.', 'error');
            return;
          }
          toast(action === 'approve' ? t.ticket_id + ' marked as Resolved' : t.ticket_id + ' sent back to staff');
          loadVerification();
          A.refreshAll();
        })
        .catch(function (err) {
          if (err.message === 'unauthorized') return;
          approve.disabled = reject.disabled = false;
          toast('Network error.', 'error');
        });
    }
    approve.addEventListener('click', function () { act('approve'); });
    reject.addEventListener('click', function () {
      if (window.confirm('Reject this After photo and send ' + t.ticket_id + ' back to staff?')) act('reject');
    });
    details.addEventListener('click', function () { A.openDrawer(t.ticket_id); });
    return card;
  }

  function loadVerification() {
    $('verify-loading').hidden = false;
    $('verify-empty').hidden = true;
    api('/api/admin/verification').then(function (r) {
      $('verify-loading').hidden = true;
      var host = $('verify-list');
      host.innerHTML = '';
      if (!r.ok) { toast(r.data.error || 'Could not load verification queue.', 'error'); return; }
      if (!r.data.tickets.length) { $('verify-empty').hidden = false; return; }
      r.data.tickets.forEach(function (t) { host.appendChild(verifyCard(t)); });
    }).catch(function (err) {
      $('verify-loading').hidden = true;
      if (err.message !== 'unauthorized') toast('Network error while loading the queue.', 'error');
    });
  }

  /* =================================================================
     Staff management
     ================================================================= */
  var staffErr = $('staff-form-error');

  function loadStaff() {
    api('/api/admin/staff').then(function (r) {
      if (!r.ok) { toast(r.data.error || 'Could not load staff.', 'error'); return; }
      var dl = $('dept-list');
      dl.innerHTML = '';
      r.data.departments.forEach(function (d) { var o = el('option'); o.value = d; dl.appendChild(o); });
      renderStaff(r.data.staff);
      A.setStaffOptions(r.data.staff);
    }).catch(function (err) { if (err.message !== 'unauthorized') toast('Network error.', 'error'); });
  }

  function renderStaff(list) {
    var body = $('staff-body');
    body.innerHTML = '';
    $('staff-empty').hidden = list.length > 0;
    list.forEach(function (m) {
      var tr = el('tr');
      tr.style.cursor = 'default';
      function cell(label, text, cls) {
        var td = el('td', cls || '', text);
        td.setAttribute('data-label', label);
        tr.appendChild(td);
        return td;
      }
      cell('Name', m.name, 'td-strong');
      cell('Login ID', m.login_id || '\u2014');
      cell('Department', m.department || '\u2014');
      cell('Open tasks', String(m.open_tasks));
      cell('Completed', String(m.done_tasks));
      var td = el('td');
      td.setAttribute('data-label', '');
      var btn = el('button', 'btn btn-sm btn-danger', 'Remove');
      btn.type = 'button';
      btn.addEventListener('click', function () { removeStaff(m, btn); });
      td.appendChild(btn);
      tr.appendChild(td);
      body.appendChild(tr);
    });
  }

  function removeStaff(m, btn) {
    var msg = 'Remove ' + m.name + '?' + (m.open_tasks ? ' Their ' + m.open_tasks + ' open ticket(s) will become unassigned.' : '');
    if (!window.confirm(msg)) return;
    btn.disabled = true;
    api('/api/admin/staff/' + m.id, { method: 'DELETE' }).then(function (r) {
      if (!r.ok) { btn.disabled = false; toast(r.data.error || 'Could not remove this staff member.', 'error'); return; }
      toast(m.name + ' was removed');
      loadStaff();
      A.refreshAll();
    }).catch(function (err) { if (err.message !== 'unauthorized') { btn.disabled = false; toast('Network error.', 'error'); } });
  }

  $('staff-form').addEventListener('submit', function (e) {
    e.preventDefault();
    staffErr.hidden = true;
    var body = {
      name: $('s-name').value.trim(),
      login_id: $('s-login').value.trim(),
      password: $('s-pass').value,
      department: $('s-dept').value.trim()
    };
    if (!body.name || !body.login_id || !body.password || !body.department) {
      staffErr.textContent = 'Please fill in all the fields.'; staffErr.hidden = false; return;
    }
    var btn = $('s-add');
    btn.disabled = true;
    api('/api/admin/staff', jsonBody('POST', body)).then(function (r) {
      btn.disabled = false;
      if (!r.ok) { staffErr.textContent = r.data.error || 'Could not add this staff member.'; staffErr.hidden = false; return; }
      toast(body.name + ' was added');
      $('staff-form').reset();
      loadStaff();
    }).catch(function (err) {
      btn.disabled = false;
      if (err.message !== 'unauthorized') { staffErr.textContent = 'Network error. Please try again.'; staffErr.hidden = false; }
    });
  });

  /* =================================================================
     Chat moderation
     ================================================================= */
  var modState = { paused: false };
  var banErr = $('ban-error');

  function renderModeration(data) {
    modState.paused = !!data.paused;
    var status = $('mod-status');
    status.textContent = data.paused ? 'Paused: only admins can send messages' : 'Live: everyone can chat';
    status.className = 'mod-status ' + (data.paused ? 'is-paused' : 'is-live');
    $('mod-pause-btn').textContent = data.paused ? 'Resume chat' : 'Pause chat';

    var body = $('ban-body');
    body.innerHTML = '';
    $('ban-empty').hidden = data.banned.length > 0;
    data.banned.forEach(function (b) {
      var tr = el('tr');
      tr.style.cursor = 'default';
      [['Student', b.name], ['Roll no.', b.roll_no], ['Banned until', fmt(b.ban_until)]].forEach(function (pair) {
        var td = el('td', '', pair[1]);
        td.setAttribute('data-label', pair[0]);
        tr.appendChild(td);
      });
      var td = el('td');
      td.setAttribute('data-label', '');
      var btn = el('button', 'btn btn-sm', 'Unban');
      btn.type = 'button';
      btn.addEventListener('click', function () {
        btn.disabled = true;
        api('/api/admin/chat/ban/' + b.student_id, { method: 'DELETE' }).then(function (r) {
          if (!r.ok) { btn.disabled = false; toast(r.data.error || 'Could not unban.', 'error'); return; }
          toast(b.name + ' can chat again');
          renderModeration(r.data);
        }).catch(function (err) { if (err.message !== 'unauthorized') { btn.disabled = false; toast('Network error.', 'error'); } });
      });
      td.appendChild(btn);
      tr.appendChild(td);
      body.appendChild(tr);
    });
  }

  function loadModeration() {
    api('/api/admin/chat/moderation').then(function (r) {
      if (r.ok) renderModeration(r.data);
      else toast(r.data.error || 'Could not load chat settings.', 'error');
    }).catch(function (err) { if (err.message !== 'unauthorized') toast('Network error.', 'error'); });
  }

  $('mod-pause-btn').addEventListener('click', function () {
    var btn = $('mod-pause-btn');
    btn.disabled = true;
    api('/api/admin/chat/pause', jsonBody('POST', { paused: !modState.paused })).then(function (r) {
      btn.disabled = false;
      if (!r.ok) { toast(r.data.error || 'Could not change chat state.', 'error'); return; }
      toast(r.data.paused ? 'Chat paused' : 'Chat resumed');
      renderModeration(r.data);
    }).catch(function (err) { btn.disabled = false; if (err.message !== 'unauthorized') toast('Network error.', 'error'); });
  });

  $('ban-form').addEventListener('submit', function (e) {
    e.preventDefault();
    banErr.hidden = true;
    var roll = $('ban-roll').value.trim();
    var days = parseInt($('ban-days').value, 10);
    if (!roll) { banErr.textContent = 'Enter the student\u2019s roll number.'; banErr.hidden = false; return; }
    if (!days || days < 1 || days > 365) { banErr.textContent = 'Days must be between 1 and 365.'; banErr.hidden = false; return; }
    var btn = $('ban-btn');
    btn.disabled = true;
    api('/api/admin/chat/ban', jsonBody('POST', { roll_no: roll, days: days })).then(function (r) {
      btn.disabled = false;
      if (!r.ok) { banErr.textContent = r.data.error || 'Could not ban this student.'; banErr.hidden = false; return; }
      toast(roll.toUpperCase() + ' is banned for ' + days + (days === 1 ? ' day' : ' days'));
      $('ban-form').reset();
      $('ban-days').value = 1;
      renderModeration(r.data);
    }).catch(function (err) {
      btn.disabled = false;
      if (err.message !== 'unauthorized') { banErr.textContent = 'Network error. Please try again.'; banErr.hidden = false; }
    });
  });
})();
