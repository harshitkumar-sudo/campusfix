/* CampusFix: Before / After photo comparison (shared by feed, track, staff and admin pages) */
(function () {
  'use strict';

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function figure(label, url, kind) {
    var fig = el('figure', 'compare-fig compare-' + kind);
    if (url) {
      var link = el('a');
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener';
      var img = el('img');
      img.src = url;
      img.alt = label + ' photo';
      img.loading = 'lazy';
      link.appendChild(img);
      fig.appendChild(link);
    } else {
      fig.appendChild(el('div', 'compare-empty', 'No photo attached'));
    }
    fig.appendChild(el('figcaption', '', label));
    return fig;
  }

  /* Returns a side-by-side Before | After block, or null when no After photo exists yet. */
  window.CFCompare = {
    build: function (t) {
      if (!t || !t.after_photo_url) return null;
      var wrap = el('div', 'compare');
      var grid = el('div', 'compare-grid');
      grid.appendChild(figure('Before', t.photo_url, 'before'));
      grid.appendChild(figure('After', t.after_photo_url, 'after'));
      wrap.appendChild(grid);
      var done = t.status === 'Resolved';
      wrap.appendChild(el('div', 'compare-note' + (done ? ' verified' : ''),
        done ? '\u2713 Fix verified by admin' : 'Awaiting admin verification'));
      return wrap;
    }
  };
})();
