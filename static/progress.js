// Shows how far a search has got while the next page is still being built. The server reports each step to
// /progress (finding the place, the Gazette's categories, notices fetched, locations checked); this polls it
// and fills the bar. Without an answer yet it creeps slowly, so the page never looks stuck.
(function () {
  var forms = document.querySelectorAll('form[action="/search"]');
  if (!forms.length) { return; }
  var timer = null;

  function build(form) {
    var box = document.createElement('div');
    box.className = 'progress';
    box.setAttribute('role', 'status');
    box.innerHTML =
      '<p class="progress-label" aria-live="polite">Starting the search</p>' +
      '<div class="progress-track" role="progressbar" aria-label="Search progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">' +
      '<span class="progress-fill"></span></div>' +
      '<p class="progress-note">A place searched for the first time takes a little longer: each notice is fetched from The Gazette and its location checked.</p>';
    (form.closest('.results-head') || form).insertAdjacentElement('afterend', box);
    box.scrollIntoView({block: 'nearest', behavior: 'smooth'});   // on a phone the bar would otherwise sit below the fold
    return box;
  }

  function start(form) {
    var place = (form.elements.place && form.elements.place.value || '').trim();
    if (!place) { return; }
    var old = document.querySelector('.progress:not(.progress-reading)');
    if (old) { old.remove(); }
    var box = build(form), label = box.querySelector('.progress-label'),
        track = box.querySelector('.progress-track'), fill = box.querySelector('.progress-fill');
    var shown = 0, began = Date.now(), button = form.querySelector('button[type="submit"]');
    if (button) { button.disabled = true; button.textContent = 'Searching'; }
    function show(pct, text) {
      shown = Math.max(shown, Math.min(pct, 100));
      fill.style.width = shown + '%';
      track.setAttribute('aria-valuenow', String(Math.round(shown)));
      if (text) { label.textContent = text; }
    }
    var seen = false;
    function poll() {
      // Stop on our own after three minutes, and as soon as the server has finished (the next page is on its way),
      // so a search that never moves on can never leave this asking the server forever.
      if (Date.now() - began > 180000) { label.textContent = 'This is taking longer than usual. Try again in a moment.'; return; }
      fetch('/progress?place=' + encodeURIComponent(place), {cache: 'no-store'})
        .then(function (r) { return r.json(); })
        .then(function (s) {
          if (s.stage) { seen = true; show(s.percent, s.label); }
          else if (seen) { show(100, 'Preparing your results'); return 'finished'; }
          else { show(Math.min(8, (Date.now() - began) / 400), 'Starting the search'); }
        })
        .catch(function () {})
        .then(function (state) { if (state !== 'finished') { timer = setTimeout(poll, 600); } });
    }
    show(2, 'Starting the search');
    timer = setTimeout(poll, 300);
  }

  forms.forEach(function (form) { form.addEventListener('submit', function () { start(form); }); });

  // Coming back with the browser's Back button can restore this page as it was left: clear the old bar.
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) { return; }
    clearTimeout(timer);
    document.querySelectorAll('.progress:not(.progress-reading)').forEach(function (b) { b.remove(); });
    document.querySelectorAll('form[action="/search"] button[type="submit"]').forEach(function (b) { b.disabled = false; b.textContent = 'Search'; });
  });
  window.addEventListener('pagehide', function () { clearTimeout(timer); });
})();
