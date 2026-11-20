(() => {
  const atlas = document.querySelector('.layered-atlas');
  if (!atlas) return;
  if (!window.L) {
    const mapElement = document.getElementById('places-map');
    if (mapElement) {
      mapElement.innerHTML = '<div class="map-load-fallback"><strong>Map unavailable</strong><span>Use the chapter list to browse family places.</span></div>';
    }
    return;
  }

  const hierarchy = JSON.parse(atlas.dataset.hierarchy || '[]');
  const theme = getComputedStyle(document.documentElement);
  const themeColor = (name, fallback) => theme.getPropertyValue(name).trim() || fallback;
  const palette = {
    navy: themeColor('--navy', '#173f6b'),
    blue: themeColor('--blue', '#286fa8'),
    bright: themeColor('--blue-bright', '#3187c8'),
    yellow: themeColor('--cornflower-yellow', '#f2c84b'),
    land: themeColor('--map-land', '#d9e7ec')
  };
  const chapterColors = {
    'overseas-origins': palette.blue,
    'footholds': palette.yellow,
    'home-communities': palette.navy
  };
  const colors = {geo: palette.bright, region: palette.yellow};
  const state = {geo: null, region: null};
  const elements = {
    breadcrumb: document.getElementById('atlas-breadcrumb'),
    level: document.getElementById('atlas-level'),
    title: document.getElementById('atlas-title'),
    summary: document.getElementById('atlas-summary'),
    choices: document.getElementById('atlas-choices')
  };
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[character]));
  const isNarrowMap = () => window.matchMedia('(max-width: 640px)').matches || document.getElementById('places-map').clientWidth < 900;

  const map = L.map('places-map', {scrollWheelZoom: false, attributionControl: false, minZoom: 2}).setView([39, -31], 3);
  const markers = L.layerGroup().addTo(map);
  fetch('/static/data/ne_110m_admin_0_countries.geojson')
    .then(response => response.json())
    .then(data => L.geoJSON(data, {
      interactive: false,
      style: {color: '#82aeca', weight: .65, fillColor: palette.land, fillOpacity: .94}
    }).addTo(map).bringToBack());

  const allCommunities = node => node.communities || node.regions.flatMap(region => region.communities);
  const fit = node => {
    const points = allCommunities(node).map(item => [item.lat, item.lng]);
    const padding = isNarrowMap() ? [28, 28] : [55, 55];
    if (points.length === 1) map.setView(points[0], 7);
    else if (points.length) map.fitBounds(points, {padding, maxZoom: 7, animate: false});
  };

  function setChapterActive(id, active) {
    elements.choices.querySelector(`[data-id="${id}"]`)?.classList.toggle('map-active', active);
    document.querySelector(`.atlas-chapter-marker[data-id="${id}"]`)?.classList.toggle('active', active);
  }

  function chapterMarker(node, index, onSelect) {
    const dominant = node.regions?.[0]?.title || 'Multiple regions';
    const compact = isNarrowMap();
    const side = compact ? 'compact' : 'label-right';
    const extraClass = node.id === 'home-communities' ? 'home-chapter' : '';
    const number = String(index + 1).padStart(2, '0');
    const callout = compact ? '' : `<span class="chapter-callout"><strong>${escapeHtml(node.title)}</strong><small>${node.communityCount} communities · ${node.events} events</small><em>Largest cluster: ${escapeHtml(dominant)}</em></span>`;
    const html = `<div class="atlas-chapter-marker ${side} ${extraClass}" data-id="${escapeHtml(node.id)}" style="--chapter-color:${chapterColors[node.id]}"><span class="chapter-dot"><b>${number}</b></span>${callout}</div>`;
    const size = compact ? [60, 60] : [280, 78];
    const anchor = compact ? [30, 30] : [27, 39];
    const marker = L.marker([node.lat, node.lng], {
      icon: L.divIcon({className: 'atlas-chapter-icon', html, iconSize: size, iconAnchor: anchor}),
      keyboard: true,
      title: `Open ${node.title}`
    }).addTo(markers);
    if (compact) {
      marker.bindTooltip(`<strong>${escapeHtml(node.title)}</strong><span>${node.communityCount} communities · ${node.events} events</span><span>Largest cluster: ${escapeHtml(dominant)}</span>`, {direction: 'top'});
    }
    marker.on('click', () => onSelect(node));
    marker.on('mouseover', () => setChapterActive(node.id, true));
    marker.on('mouseout', () => setChapterActive(node.id, false));
  }

  function draw(nodes, kind, onSelect) {
    markers.clearLayers();
    nodes.forEach((node, index) => {
      if (kind === 'root') {
        chapterMarker(node, index, onSelect);
        return;
      }
      const radius = Math.max(10, Math.min(28, 8 + Math.sqrt(node.events || node.count) * 1.15));
      const communities = node.communityCount || 1;
      const marker = L.circleMarker([node.lat, node.lng], {
        radius, color: '#fff', weight: 3, fillColor: colors[kind], fillOpacity: .94
      }).addTo(markers);
      marker.bindTooltip(`<strong>${escapeHtml(node.title || node.name)}</strong><span>${communities} ${communities === 1 ? 'community' : 'communities'} · ${node.events || node.count} events</span>`, {direction: 'top'});
      marker.on('click', () => onSelect(node));
    });
  }

  function buttonMarkup(node, kind, index) {
    const count = kind === 'community'
      ? `${node.people} people · ${node.count} events`
      : `${node.communityCount} communities · ${node.events} events`;
    const preface = kind === 'region' ? node.summary : (node.preface || node.summary);
    const branchTags = kind === 'region' && node.familyBranches?.length
      ? `<span class="atlas-branch-tags">${node.familyBranches.map(branch => `<b>${escapeHtml(branch.label)}</b>`).join('')}</span>`
      : '';
    const label = kind === 'geography' ? `${String(index + 1).padStart(2, '0')} / chapter` : kind;
    return `<button type="button" data-id="${escapeHtml(node.id || node.slug)}"><span>${label}</span><strong>${escapeHtml(node.title || node.name)}</strong>${preface ? `<p>${escapeHtml(preface)}</p>` : ''}${branchTags}<small>${count}</small><i>Open →</i></button>`;
  }

  function setBreadcrumb() {
    elements.breadcrumb.innerHTML = '<button data-level="root">Family atlas</button>';
    if (state.geo) elements.breadcrumb.insertAdjacentHTML('beforeend', `<span>/</span><button data-level="geo">${escapeHtml(state.geo.title)}</button>`);
    if (state.region) elements.breadcrumb.insertAdjacentHTML('beforeend', `<span>/</span><strong>${escapeHtml(state.region.title)}</strong>`);
    elements.breadcrumb.querySelector('[data-level="root"]').onclick = showRoot;
    elements.breadcrumb.querySelector('[data-level="geo"]')?.addEventListener('click', () => showGeo(state.geo));
  }

  function bindCards(nodes, kind, handler) {
    elements.choices.innerHTML = nodes.map((node, index) => buttonMarkup(node, kind, index)).join('');
    elements.choices.querySelectorAll('[data-id]').forEach(button => {
      const node = nodes.find(item => (item.id || item.slug) === button.dataset.id);
      button.onclick = () => handler(node);
      if (kind === 'geography') {
        button.onmouseenter = () => setChapterActive(node.id, true);
        button.onmouseleave = () => setChapterActive(node.id, false);
        button.onfocus = () => setChapterActive(node.id, true);
        button.onblur = () => setChapterActive(node.id, false);
      }
    });
  }

  function showRoot() {
    state.geo = null;
    state.region = null;
    setBreadcrumb();
    elements.level.textContent = 'GEOGRAPHIES';
    elements.title.textContent = 'Three chapters of place';
    elements.summary.textContent = 'Choose a chapter to move from the family’s broad geography into its regions and communities.';
    bindCards(hierarchy, 'geography', showGeo);
    draw(hierarchy, 'root', showGeo);
    map.invalidateSize();
    map.fitBounds(hierarchy.map(node => [node.lat, node.lng]), {paddingTopLeft: [45, 65], paddingBottomRight: [isNarrowMap() ? 45 : 280, 65], maxZoom: 3});
  }

  function showGeo(geo) {
    state.geo = geo;
    state.region = null;
    setBreadcrumb();
    elements.level.textContent = 'REGIONS';
    elements.title.textContent = geo.title;
    elements.summary.textContent = geo.familySummary || geo.summary;
    bindCards(geo.regions, 'region', showRegion);
    draw(geo.regions, 'geo', showRegion);
    fit(geo);
  }

  function showRegion(region) {
    state.region = region;
    setBreadcrumb();
    elements.level.textContent = 'COMMUNITIES';
    elements.title.textContent = region.title;
    elements.summary.textContent = region.summary;
    bindCards(region.communities, 'community', community => { window.location.href = `/places/${community.slug}`; });
    draw(region.communities.map(item => ({...item, events: item.count})), 'region', community => { window.location.href = `/places/${community.slug}`; });
    fit(region);
  }

  showRoot();
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      map.invalidateSize();
      if (state.region) showRegion(state.region);
      else if (state.geo) showGeo(state.geo);
      else showRoot();
    }, 160);
  });
})();
