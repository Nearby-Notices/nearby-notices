// When this site is shown inside its GitHub Pages front (for networks that block newly registered domains),
// links to other sites open in a new tab, since most of them refuse to load inside a frame, and the front is told
// the app has loaded so it can hide its fallback message.
(function () {
  if (window.top === window) { return; }
  var FRONT = 'https://nearby-notices.github.io';
  document.addEventListener('click', function (e) {
    var a = e.target.closest ? e.target.closest('a[href]') : null;
    if (a && a.host && a.host !== location.host) { a.target = '_blank'; a.rel = 'noopener'; }
  }, true);
  try { window.parent.postMessage({nn: 'ready', path: location.pathname + location.search}, FRONT); } catch (err) { /* not framed by the front */ }
})();
