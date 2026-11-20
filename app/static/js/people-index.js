// Client-side faceting for the people index. The whole list is already in the
// page, so filtering is instant and works without another round trip.
(() => {
  const list = document.getElementById('surname-list');
  if (!list) return;
  const groups = [...list.querySelectorAll('.surname-group')];
  const count = document.getElementById('result-count');
  const empty = document.getElementById('no-results');
  const filters = {branch: '', country: '', evidence: ''};

  function apply() {
    let shown = 0;
    groups.forEach(group => {
      let visibleInGroup = 0;
      group.querySelectorAll('li').forEach(item => {
        const ok = (!filters.branch || item.dataset.branch === filters.branch)
          && (!filters.country || item.dataset.country === filters.country)
          && (!filters.evidence || item.dataset.evidence === filters.evidence);
        item.hidden = !ok;
        if (ok) visibleInGroup += 1;
      });
      group.hidden = visibleInGroup === 0;
      shown += visibleInGroup;
    });
    const active = Object.values(filters).some(Boolean);
    count.textContent = active
      ? `${shown} ${shown === 1 ? 'relative' : 'relatives'} match`
      : '';
    empty.hidden = shown !== 0;
    if (narrow.matches) {
      groups.forEach(group => setOpen(group, active && !group.hidden));
    }
  }


  // On a phone the full index is a ~116,000px wall of cards. Collapse each
  // surname to a tappable row and let people open the ones they care about.
  // Desktop keeps the full grid.
  const narrow = window.matchMedia('(max-width: 900px)');

  function groupCount(group) {
    return group.querySelectorAll('li:not([hidden])').length;
  }

  function setOpen(group, open) {
    group.classList.toggle('is-open', open);
    const toggle = group.querySelector('.group-toggle');
    if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function buildToggles() {
    groups.forEach(group => {
      if (group.querySelector('.group-toggle')) return;
      const header = group.querySelector('header');
      const list = group.querySelector('ul');
      if (!header || !list) return;
      const id = `${group.id}-list`;
      list.id = id;
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'group-toggle';
      toggle.setAttribute('aria-controls', id);
      toggle.setAttribute('aria-label', `Show relatives in the ${header.querySelector('h2').textContent} family`);
      toggle.setAttribute('aria-expanded', 'false');
      toggle.innerHTML = '<span aria-hidden="true"></span>';
      toggle.addEventListener('click', () => setOpen(group, !group.classList.contains('is-open')));
      header.appendChild(toggle);
      header.addEventListener('click', event => {
        // The toggle handles its own clicks; without this guard the event bubbles
        // here and immediately flips the group back shut.
        if (!narrow.matches || event.target.closest('a') || event.target.closest('.group-toggle')) return;
        setOpen(group, !group.classList.contains('is-open'));
      });
    });
  }

  function applyCollapse() {
    document.body.classList.toggle('groups-collapsible', narrow.matches);
    if (!narrow.matches) return;
    const targeted = window.location.hash.replace('#', '');
    groups.forEach(group => setOpen(group, group.id === targeted));
    const target = targeted && document.getElementById(targeted);
    if (target) target.scrollIntoView();
  }

  buildToggles();
  applyCollapse();
  narrow.addEventListener('change', applyCollapse);
  window.addEventListener('hashchange', applyCollapse);

  document.querySelectorAll('.chips').forEach(row => {
    const facet = row.dataset.facet;
    row.querySelectorAll('.chip').forEach(c => c.setAttribute('aria-pressed', String(c.classList.contains('active'))));
    row.querySelectorAll('.chip').forEach(chip => chip.addEventListener('click', () => {
      filters[facet] = chip.dataset.value;
      row.querySelectorAll('.chip').forEach(c => {
        c.classList.toggle('active', c === chip);
        c.setAttribute('aria-pressed', String(c === chip));
      });
      apply();
    }));
  });

  document.getElementById('clear-filters')?.addEventListener('click', () => {
    Object.keys(filters).forEach(key => { filters[key] = ''; });
    document.querySelectorAll('.chips').forEach(row => {
      row.querySelectorAll('.chip').forEach((c, i) => {
        c.classList.toggle('active', i === 0);
        c.setAttribute('aria-pressed', String(i === 0));
      });
    });
    apply();
  });
})();
