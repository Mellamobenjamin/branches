// Search works independently of the optional map; submitting always has a
// server-rendered destination, including when JavaScript or autocomplete fails.
(() => {
  const input = document.getElementById('home-person-search') || document.getElementById('person-search');
  const results = document.getElementById('home-search-results') || document.getElementById('search-results');
  if (!input || !results) return;
  let timer;
  let requestNumber = 0;
  const close = () => { results.classList.remove('open'); results.replaceChildren(); };
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const currentRequest = ++requestNumber;
    const query = input.value.trim();
    close();
    if (query.length < 2) return;
    timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        if (!response.ok) throw new Error('Search unavailable');
        const rows = await response.json();
        if (currentRequest !== requestNumber) return;
        results.replaceChildren();
        rows.forEach(row => {
          const link = document.createElement('a');
          link.href = row.kind === 'surname' ? `/surnames/${encodeURIComponent(row.slug)}` : `/people/${encodeURIComponent(row.id)}`;
          const name = document.createElement('span');
          name.textContent = row.kind === 'surname' ? `The ${row.name} family` : row.name;
          const detail = document.createElement('small');
          detail.textContent = row.kind === 'surname' ? `${row.count} relatives · ${row.span || 'Dates incomplete'}` : `${row.years || 'Dates incomplete'} · ${row.birthPlace || 'Birthplace not recorded'}`;
          link.append(name, detail);
          results.append(link);
        });
        if (!rows.length) results.textContent = 'No matching public relatives. Try another spelling or browse all relatives.';
        results.classList.add('open');
      } catch {
        if (currentRequest === requestNumber) close();
      }
    }, 180);
  });
  input.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown' && results.querySelector('a')) {
      event.preventDefault(); results.querySelector('a').focus();
    }
  });
  results.addEventListener('keydown', event => {
    const links = [...results.querySelectorAll('a')];
    const index = links.indexOf(document.activeElement);
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const next = index + (event.key === 'ArrowDown' ? 1 : -1);
      if (next < 0) input.focus(); else links[Math.min(next, links.length - 1)]?.focus();
    }
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') { ++requestNumber; close(); } });
  document.addEventListener('click', event => { if (!event.target.closest('.home-search, .search-box')) { ++requestNumber; close(); } });
})();
