/* Auto-mode persistence across pages: ?source=auto is remembered in
   sessionStorage and re-applied to the URL and to nav links, so browsing
   from page to page keeps the dev/test source flag. */
(function () {
  const params = new URLSearchParams(window.location.search);
  if (params.get('source') === 'auto') {
    sessionStorage.setItem('examradar_source', 'auto');
  } else if (sessionStorage.getItem('examradar_source') === 'auto') {
    params.set('source', 'auto');
    const qs = params.toString();
    history.replaceState(null, '',
      window.location.pathname + (qs ? '?' + qs : '') + window.location.hash);
  }

  window.examRadarSource = function () {
    return new URLSearchParams(window.location.search).get('source') === 'auto'
      ? 'auto' : 'real';
  };

  function rewriteLinks() {
    document.querySelectorAll('nav a, .quick-links a').forEach(a => {
      const url = new URL(a.href, window.location.origin);
      if (url.origin !== window.location.origin) return;
      url.searchParams.set('source', 'auto');
      a.href = url.pathname + url.search + url.hash;
    });
  }

  if (window.examRadarSource() === 'auto') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', rewriteLinks);
    } else {
      rewriteLinks();
    }
  }
})();
