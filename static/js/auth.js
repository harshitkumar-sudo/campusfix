/* CampusFix: student login + register (Part 4) */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var errEl = $('auth-error'), btn = $('auth-btn');
  var loginForm = $('student-login-form'), regForm = $('register-form');

  function showError(msg) { errEl.textContent = msg; errEl.hidden = false; }
  function setBusy(busy, label, busyLabel) {
    btn.disabled = busy;
    btn.innerHTML = '';
    if (busy) {
      var sp = document.createElement('span');
      sp.className = 'spinner';
      btn.appendChild(sp);
      btn.appendChild(document.createTextNode(' ' + busyLabel));
    } else {
      btn.textContent = label;
    }
  }

  function send(url, body, label, busyLabel) {
    errEl.hidden = true;
    setBusy(true, label, busyLabel);
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (r) {
        if (r.ok) { window.location.href = '/'; return; }
        setBusy(false, label, busyLabel);
        showError(r.data.error || 'Something went wrong. Please try again.');
      })
      .catch(function () {
        setBusy(false, label, busyLabel);
        showError('Network error. Please check your connection.');
      });
  }

  if (loginForm) {
    loginForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var roll = $('roll_no').value.trim(), pw = $('password').value;
      if (!roll || !pw) return showError('Please enter your roll number and password.');
      send('/api/student/login', { roll_no: roll, password: pw }, 'Sign in', 'Signing in\u2026');
    });
  }

  if (regForm) {
    regForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var name = $('name').value.trim(), roll = $('roll_no').value.trim();
      var pw = $('password').value, pw2 = $('password2').value;
      if (name.length < 2) return showError('Please enter your full name.');
      if (roll.length < 3) return showError('Please enter a valid roll number.');
      if (pw.length < 6) return showError('Password must be at least 6 characters.');
      if (pw !== pw2) return showError('Passwords do not match.');
      send('/api/student/register', { name: name, roll_no: roll, password: pw }, 'Create account', 'Creating account\u2026');
    });
  }
})();
