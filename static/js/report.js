/* CampusFix: report page logic (Part 2) */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var form = $('report-form'), categoryEl = $('category'), wingEl = $('wing'), roomEl = $('room');
  var descEl = $('description'), photoEl = $('photo'), previewWrap = $('photo-preview-wrap');
  var previewImg = $('photo-preview'), removeBtn = $('photo-remove'), errorEl = $('form-error');
  var submitBtn = $('submit-btn'), counterEl = $('desc-count'), loadingEl = $('meta-loading');
  var formCard = $('form-card'), successCard = $('success-card'), ticketIdEl = $('success-ticket-id');
  var copyBtn = $('copy-btn'), trackLink = $('track-link'), againBtn = $('again-btn');

  var MAX_PHOTO = 5 * 1024 * 1024;
  var meta = null;
  var previewUrl = null;

  /* ---------- helpers ---------- */
  function showError(msg, withRetry) {
    errorEl.textContent = msg;
    if (withRetry) {
      var retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'btn btn-sm';
      retry.style.marginLeft = '12px';
      retry.textContent = 'Retry';
      retry.addEventListener('click', loadMeta);
      errorEl.appendChild(retry);
    }
    errorEl.hidden = false;
  }
  function clearError() { errorEl.hidden = true; errorEl.textContent = ''; }

  function fillSelect(select, placeholder, items, labelFn) {
    select.innerHTML = '';
    var first = document.createElement('option');
    first.value = '';
    first.textContent = placeholder;
    select.appendChild(first);
    items.forEach(function (item) {
      var o = document.createElement('option');
      o.value = item;
      o.textContent = labelFn ? labelFn(item) : item;
      select.appendChild(o);
    });
  }

  function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    submitBtn.innerHTML = '';
    if (isLoading) {
      var sp = document.createElement('span');
      sp.className = 'spinner';
      submitBtn.appendChild(sp);
      submitBtn.appendChild(document.createTextNode(' Submitting\u2026'));
    } else {
      submitBtn.textContent = 'Submit Complaint';
    }
  }

  /* ---------- load dropdown data ---------- */
  function loadMeta() {
    clearError();
    form.hidden = true;
    loadingEl.hidden = false;
    fetch('/api/meta')
      .then(function (res) {
        if (!res.ok) throw new Error('bad status');
        return res.json();
      })
      .then(function (data) {
        meta = data;
        fillSelect(categoryEl, 'Select a category', meta.categories);
        fillSelect(wingEl, 'Select a wing', meta.wings, function (w) { return 'Wing ' + w; });
        fillSelect(roomEl, 'Select a wing first', []);
        roomEl.disabled = true;
        loadingEl.hidden = true;
        form.hidden = false;
      })
      .catch(function () {
        loadingEl.hidden = true;
        showError('Could not load the form options. Please check your connection.', true);
      });
  }

  wingEl.addEventListener('change', function () {
    var wing = wingEl.value;
    if (!wing || !meta) {
      fillSelect(roomEl, 'Select a wing first', []);
      roomEl.disabled = true;
      return;
    }
    fillSelect(roomEl, 'Select a room', meta.rooms[wing] || [], function (r) { return 'Room ' + r; });
    roomEl.disabled = false;
  });

  descEl.addEventListener('input', function () { counterEl.textContent = descEl.value.length; });

  /* ---------- photo preview ---------- */
  function clearPhoto() {
    photoEl.value = '';
    previewWrap.hidden = true;
    if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
    previewImg.removeAttribute('src');
  }

  photoEl.addEventListener('change', function () {
    clearError();
    var file = photoEl.files && photoEl.files[0];
    if (!file) { clearPhoto(); return; }
    if (['image/png', 'image/jpeg'].indexOf(file.type) === -1) {
      clearPhoto();
      showError('Photo must be a PNG or JPG image.');
      return;
    }
    if (file.size > MAX_PHOTO) {
      clearPhoto();
      showError('Photo is too large. Please choose an image under 5MB.');
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    previewImg.src = previewUrl;
    previewWrap.hidden = false;
  });
  removeBtn.addEventListener('click', clearPhoto);

  /* ---------- submit ---------- */
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    clearError();

    if (!categoryEl.value) return showError('Please choose a category.');
    if (!wingEl.value) return showError('Please choose a wing.');
    if (!roomEl.value) return showError('Please choose a room.');
    if (!descEl.value.trim()) return showError('Please describe the problem.');

    var fd = new FormData(form);
    if (!photoEl.files || !photoEl.files.length) fd.delete('photo');

    setLoading(true);
    fetch('/api/tickets', { method: 'POST', body: fd })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          return { ok: res.ok, status: res.status, data: data };
        });
      })
      .then(function (r) {
        setLoading(false);
        if (r.status === 401) { window.location.href = '/login'; return; }
        if (!r.ok) {
          showError(r.data.error || 'Something went wrong. Please try again.');
          window.scrollTo({ top: 0, behavior: 'smooth' });
          return;
        }
        ticketIdEl.textContent = r.data.ticket_id;
        trackLink.href = '/track?id=' + encodeURIComponent(r.data.ticket_id);
        formCard.hidden = true;
        successCard.hidden = false;
        window.scrollTo({ top: 0, behavior: 'smooth' });
      })
      .catch(function () {
        setLoading(false);
        showError('Network error. Please check your connection and try again.');
      });
  });

  /* ---------- success actions ---------- */
  copyBtn.addEventListener('click', function () {
    var text = ticketIdEl.textContent;
    function done() {
      copyBtn.textContent = 'Copied!';
      setTimeout(function () { copyBtn.textContent = 'Copy ID'; }, 1800);
    }
    if (navigator.clipboard && window.isSecureContext !== false) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else {
      fallback();
    }
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); done(); } catch (err) { /* ignore */ }
      document.body.removeChild(ta);
    }
  });

  againBtn.addEventListener('click', function () {
    form.reset();
    clearPhoto();
    clearError();
    counterEl.textContent = '0';
    fillSelect(roomEl, 'Select a wing first', []);
    roomEl.disabled = true;
    successCard.hidden = true;
    formCard.hidden = false;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  loadMeta();
})();
