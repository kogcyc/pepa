function searchPages(pages, query) {
  const terms = query.toLowerCase().trim().split(/\s+/u).filter(Boolean);
  if (!terms.length) return [];
  return pages.filter(page => {
    const text = `${page.title} ${page.text}`.toLowerCase();
    return terms.every(term => text.includes(term));
  });
}

function snippet(text, query) {
  const positions = query.toLowerCase().trim().split(/\s+/u)
    .map(term => text.toLowerCase().indexOf(term)).filter(n => n >= 0);
  const start = Math.max(0, (positions.length ? Math.min(...positions) : 0) - 60);
  const end = Math.min(text.length, start + 220);
  return `${start ? '…' : ''}${text.slice(start, end)}${end < text.length ? '…' : ''}`;
}

if (typeof module !== 'undefined') module.exports = {searchPages, snippet};
if (typeof document !== 'undefined') {
  const form = document.getElementById('search-form');
  const input = document.getElementById('search-query');
  const status = document.getElementById('search-status');
  const results = document.getElementById('search-results');
  function render() {
    const query = input.value.trim();
    results.replaceChildren();
    if (!query) {
      status.textContent = 'Enter words to search the website.';
      return;
    }
    if (!Array.isArray(window.SITE_SEARCH_INDEX)) {
      status.textContent = 'Search could not load. Please reload and try again.';
      return;
    }
    const matches = searchPages(window.SITE_SEARCH_INDEX, query);
    status.textContent = matches.length
      ? `${matches.length} result${matches.length === 1 ? '' : 's'} for “${query}”.`
      : `No results for “${query}”. Try different words.`;
    for (const page of matches) {
      const url = new URL(page.url, window.location.href);
      if (!['http:', 'https:', 'file:'].includes(url.protocol)) continue;
      const item = document.createElement('li');
      const link = document.createElement('a');
      link.href = url.href;
      link.className = 'text-xl font-bold underline underline-offset-4';
      link.textContent = page.title;
      const excerpt = document.createElement('p');
      excerpt.className = 'mt-2 leading-relaxed text-slate-700';
      excerpt.textContent = snippet(page.text, query);
      item.append(link, excerpt);
      results.append(item);
    }
  }
  function readQuery() {
    input.value = new URLSearchParams(window.location.search).get('q') || '';
    render();
  }
  form.addEventListener('submit', event => {
    event.preventDefault();
    const url = new URL(window.location.href);
    if (input.value.trim()) url.searchParams.set('q', input.value.trim());
    else url.searchParams.delete('q');
    window.history.pushState(null, '', url);
    render();
  });
  window.addEventListener('popstate', readQuery);
  readQuery();
}
