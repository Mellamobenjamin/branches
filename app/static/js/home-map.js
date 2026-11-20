(() => {
  const element = document.getElementById('heritage-map-canvas');
  if (!element) return;
  if (!window.L) {
    const summary = document.getElementById('stage-summary');
    const method = document.getElementById('stage-method');
    if (summary) summary.textContent = 'The map is unavailable. You can browse all places or search for a relative below.';
    if (method) method.textContent = 'Map assets could not be loaded in this browser session.';
    element.innerHTML = '<div class="map-load-fallback"><strong>Map unavailable</strong><span>The family tree, people index, and place pages are still available.</span></div>';
    return;
  }
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[character]));
  const css = getComputedStyle(document.documentElement);
  const token = (name, fallback) => css.getPropertyValue(name).trim() || fallback;

  const colors = {
    origins: token('--brass', '#8a6220'),
    gateways: token('--water', '#4a6e86'),
    homesteads: token('--juniper', '#2f6152'),
  };
  // Branch identity has its own scale so it never collides with the evidence
  // vocabulary (juniper / brass / iron oxide). Lightened for the dark ocean and
  // luminance-staggered so the four separate in greyscale too.
  const familyStreamColors = [
    token('--stream-1', '#6798a5'),
    token('--stream-2', '#7ec1ad'),
    token('--stream-3', '#ead0a4'),
    token('--stream-4', '#f9edea'),
  ];
  const map = L.map(element, {
    zoomControl: false,
    attributionControl: false,
    scrollWheelZoom: false,
    minZoom: 2,
    maxZoom: 9,
  }).setView([46, -10], 3);
  L.control.zoom({position: 'topright'}).addTo(map);
  const markerLayer = L.layerGroup().addTo(map);
  const routeLayer = L.layerGroup().addTo(map);
  const storyLayer = L.layerGroup().addTo(map);
  const countLayer = L.layerGroup().addTo(map);
  let geography;
  let activeStage = 'origins';
  let markerByName = new Map();
  let placed = [];
  let arcs = [];
  let origins = [];
  let flags = [];

  const MARKER_LIMIT = 10;
  const LIST_LIMIT = 5;
  const LABEL_LIMIT = 6;

  map.on('zoomend moveend resize', () => {
    if (geography) layoutLabels();
  });

  function overlayInsets() {
    if (window.matchMedia('(max-width: 1100px)').matches) {
      return {topLeft: L.point(24, 24), bottomRight: L.point(24, 24)};
    }
    const box = element.getBoundingClientRect();
    const story = document.querySelector('.home-story-panel')?.getBoundingClientRect();
    let left = 48;
    let right = 48;
    let bottom = 150;
    if (story?.width > box.width * .7) {
      bottom = Math.min(story.height + 180, box.height * .58);
    } else if (story) {
      const sitsLeft = story.left - box.left < box.width / 2;
      if (sitsLeft) left = Math.min(story.right - box.left + 32, box.width * .42);
      else right = Math.min(box.right - story.left + 32, box.width * .42);
    }
    return {
      topLeft: L.point(left, 120),
      bottomRight: L.point(right, bottom),
    };
  }

  function frameStage(items, stage, animate) {
    const points = items.map(item => [item.lat, item.lng]);
    (stage.familyStreams || []).forEach(stream => {
      points.push([stream.fromLat, stream.fromLng]);
      points.push([stream.toLat, stream.toLng]);
    });
    (stage.highlights || []).forEach(item => points.push([item.lat, item.lng]));
    if (!points.length) return;
    const insets = overlayInsets();
    map.fitBounds(L.latLngBounds(points), {
      animate,
      paddingTopLeft: insets.topLeft,
      paddingBottomRight: insets.bottomRight,
      maxZoom: stage.familyStreams && stage.familyStreams.length ? 5 : 7,
    });
  }

  // Labels used to alternate left/right by rank, which collides as soon as two
  // places sit near each other. Reserve space in screen coordinates instead and
  // drop any label that cannot find a clear box.
  // Every permanent label on the map - place names, family streams, origin
  // points - competes for the same screen space, so they are all placed in one
  // pass that reserves boxes and drops anything that cannot find a clear spot.
  function labelBudget(size) {
    return Math.max(3, Math.round((size.x * size.y) / 45000));
  }

  function layoutLabels() {
    countLayer.clearLayers();
    const size = map.getSize();
    let budget = labelBudget(size);
    const boxes = [];
    const reserve = box => { boxes.push(box); };
    const clear = box => box.l >= 4 && box.r <= size.x - 4 && box.t >= 4 && box.b <= size.y - 4
      && !boxes.some(other =>
        !(box.r < other.l || box.l > other.r || box.b < other.t || box.t > other.b));

    // The story panel and search card sit on top of the map, so anything placed
    // beneath them is invisible. Reserve their footprints before placing labels.
    const mapBox = element.getBoundingClientRect();
    ['.home-story-panel', '.home-discovery', '.home-map-key']
      .forEach(selector => {
        const node = document.querySelector(selector);
        if (!node) return;
        const rect = node.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        reserve({
          l: rect.left - mapBox.left - 8, r: rect.right - mapBox.left + 8,
          t: rect.top - mapBox.top - 8, b: rect.bottom - mapBox.top + 8,
        });
      });

    const markerBoxes = placed.map(({marker}) => {
      const point = map.latLngToContainerPoint(marker.getLatLng());
      return {l: point.x - 15, r: point.x + 15, t: point.y - 15, b: point.y + 15};
    });
    markerBoxes.forEach(reserve);
    origins.forEach(({marker}) => {
      const point = map.latLngToContainerPoint(marker.getLatLng());
      reserve({l: point.x - 12, r: point.x + 12, t: point.y - 12, b: point.y + 12});
    });
    flags.forEach(({marker}) => {
      const point = map.latLngToContainerPoint(marker.getLatLng());
      reserve({l: point.x - 8, r: point.x + 12, t: point.y - 30, b: point.y + 6});
    });

    // Shared placement: try each side, take the first clear box, spend a budget slot.
    function attach(marker, text, klass, width, anchor, offsets) {
      if (budget <= 0) return false;
      for (const [direction, box, offset] of offsets) {
        if (!clear(box)) continue;
        reserve(box);
        marker.bindTooltip(text, {permanent: true, direction, offset, className: klass});
        budget -= 1;
        return true;
      }
      return false;
    }

    // Broad origins first: they anchor the symbolic streams.
    origins.forEach(({marker, text}) => {
      marker.unbindTooltip();
      const point = map.latLngToContainerPoint(marker.getLatLng());
      const w = text.length * 5.9 + 16;
      const options = [
        ['top', {l: point.x - w / 2, r: point.x + w / 2, t: point.y - 32, b: point.y - 12}],
        ['bottom', {l: point.x - w / 2, r: point.x + w / 2, t: point.y + 12, b: point.y + 32}],
        ['right', {l: point.x + 14, r: point.x + 14 + w, t: point.y - 10, b: point.y + 10}],
        ['left', {l: point.x - 14 - w, r: point.x - 14, t: point.y - 10, b: point.y + 10}],
      ];
      for (const [direction, box] of options) {
        if (!clear(box) || budget <= 0) continue;
        reserve(box);
        budget -= 1;
        marker.bindTooltip(text, {
          permanent: true, direction, className: 'family-stream-origin-label',
          offset: direction === 'top' ? [0, -6] : direction === 'bottom' ? [0, 6]
                : direction === 'right' ? [6, 0] : [-6, 0],
        });
        return;
      }
    });

    // Narrative flags are the chapter's editorial content, so they get space
    // before the generic place names.
    flags.forEach(({marker, text}) => {
      marker.unbindTooltip();
      // The family-stream overview already labels its four branches. Keep story
      // flags clickable there, but reveal their labels on hover to avoid a knot
      // of permanent labels around the broad U.S. footholds.
      if (activeStage === 'gateways' && geography[activeStage]?.familyStreams?.length) {
        marker.bindTooltip(text, {direction: 'top', className: 'home-story-flag-label'});
        return;
      }
      const point = map.latLngToContainerPoint(marker.getLatLng());
      const w = text.length * 7.4 + 24;
      attach(marker, text, 'home-story-flag-label', w, point, [
        ['right', {l: point.x + 12, r: point.x + 12 + w, t: point.y - 34, b: point.y - 14}, [10, -12]],
        ['left', {l: point.x - 12 - w, r: point.x - 12, t: point.y - 34, b: point.y - 14}, [-10, -12]],
        ['top', {l: point.x - w / 2, r: point.x + w / 2, t: point.y - 52, b: point.y - 32}, [4, -30]],
      ]);
    });

    // Stream details live in hover tooltips so the Atlantic reads as movement,
    // not a field of floating labels.

    // Place names last.
    placed.forEach(({marker, item}, rank) => {
      marker.unbindTooltip();
      if (activeStage === 'gateways' && geography[activeStage]?.familyStreams?.length) {
        marker.bindTooltip(item.name, {direction: 'top', className: 'home-place-label'});
        return;
      }
      if (rank >= LABEL_LIMIT) return;
      const point = map.latLngToContainerPoint(marker.getLatLng());
      const w = item.name.length * 7.8 + 28;
      const order = point.x > size.x / 2 ? ['left', 'right'] : ['right', 'left'];
      for (const direction of order) {
        const left = direction === 'right' ? point.x + 18 : point.x - 18 - w;
        const box = {l: left, r: left + w, t: point.y - 11, b: point.y + 11};
        const own = markerBoxes[rank];
        const others = boxes.filter(candidate => candidate !== own);
        const hits = others.some(other =>
          !(box.r < other.l || box.l > other.r || box.b < other.t || box.t > other.b));
        if (hits || box.l < 4 || box.r > size.x - 4 || budget <= 0) continue;
        reserve(box);
        budget -= 1;
        marker.bindTooltip(item.name, {
          permanent: true, direction,
          offset: direction === 'right' ? [10, 0] : [-10, 0],
          className: 'home-place-label',
        });
        return;
      }
    });
  }

  const panel = {
    root: document.querySelector('.home-story-panel'),
    eyebrow: document.getElementById('stage-eyebrow'),
    title: document.getElementById('stage-title'),
    summary: document.getElementById('stage-summary'),
    anecdote: document.getElementById('stage-anecdote'),
    listLabel: document.getElementById('stage-list-label'),
    places: document.getElementById('stage-place-list'),
    method: document.getElementById('stage-method'),
    reset: document.getElementById('stage-reset'),
    link: document.getElementById('stage-link'),
    routeKey: document.getElementById('route-key'),
    streamLegend: document.getElementById('family-stream-legend'),
  };

  function markPanelUpdated(view) {
    panel.root.dataset.view = view;
    panel.root.classList.remove('panel-updated');
    requestAnimationFrame(() => panel.root.classList.add('panel-updated'));
  }

  function selectMarker(name = '') {
    placed.forEach(({marker, item}) => {
      marker.getElement()?.classList.toggle('is-selected', item.name === name);
    });
  }

  function syncLocation(item = null) {
    const params = new URLSearchParams(window.location.search);
    params.set('stage', activeStage);
    if (item) params.set('place', item.slug);
    else params.delete('place');
    const query = params.toString();
    window.history.replaceState({}, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
  }

  function markerIcon(item, color, rank) {
    const size = Math.max(14, Math.min(38, 11 + Math.sqrt(item.people) * 2.9));
    return L.divIcon({
      className: 'home-map-marker',
      html: `<i style="--marker-size:${size}px;--marker-color:${color}"></i>`,
      iconSize: [size + 6, size + 6],
      iconAnchor: [(size + 6) / 2, (size + 6) / 2],
    });
  }

  function yearSpan(item) {
    if (!item.firstYear && !item.lastYear) return 'Dates vary';
    if (item.firstYear === item.lastYear) return String(item.firstYear);
    return `${item.firstYear || '?'}–${item.lastYear || '?'}`;
  }

  function evidenceText(item) {
    if (activeStage === 'origins') {
      return `${item.people} relatives have a birth record connected to this place.`;
    }
    if (activeStage === 'gateways') {
      const direct = item.evidence['documented-arrival'] || 0;
      const inferred = item.evidence['first-us-record'] || 0;
      const parts = [];
      if (direct) parts.push(`${direct} arrival connection${direct === 1 ? '' : 's'}`);
      if (inferred) parts.push(`${inferred} first American place${inferred === 1 ? '' : 's'}`);
      return `${item.people} relatives connect to this area through ${parts.join(' and ') || 'the family tree'}.`;
    }
    return `${item.records} life-event records connect ${item.people} relatives to this community.`;
  }

  function naturalList(values) {
    if (values.length < 2) return values.join('');
    if (values.length === 2) return values.join(' and ');
    return `${values.slice(0, -1).join(', ')}, and ${values[values.length - 1]}`;
  }

  function showItem(item) {
    markPanelUpdated('detail');
    selectMarker(item.name);
    panel.reset.hidden = false;
    panel.reset.textContent = `← Back to ${geography[activeStage].eyebrow.toLowerCase()}`;
    panel.title.textContent = item.name;
    panel.summary.textContent = evidenceText(item);
    const merged = (item.alsoKnown || []).length
      ? `<span title="Shown as one point on the map">with ${escapeHtml(item.alsoKnown.join(', '))}</span>`
      : '';
    const familyLines = (item.familyBranches || []).map(branch => branch.label.replace(/ branch$/i, ''));
    const branchChips = activeStage === 'origins'
      ? familyLines.map(line => `<span class="place-family-line">${escapeHtml(line)} family line</span>`).join('')
      : '';
    panel.listLabel.textContent = 'This place at a glance';
    panel.places.innerHTML = `<span>${item.people} people</span><span>${item.records} records</span><span>${yearSpan(item)}</span>${merged}${branchChips}`;
    const chronology = item.firstYear
      ? `${item.name} enters this family record in ${item.firstYear}${item.lastYear && item.lastYear !== item.firstYear ? ` and continues through ${item.lastYear}` : ''}.`
      : geography[activeStage].anecdote;
    const branchStory = activeStage === 'origins' && familyLines.length
      ? ` Relatives from this origin connect forward to the ${naturalList(familyLines)} family ${familyLines.length === 1 ? 'line' : 'lines'}.`
      : '';
    panel.anecdote.textContent = chronology + branchStory;
    panel.method.textContent = geography[activeStage].method;
    const marker = markerByName.get(item.name);
    if (marker) map.panTo(marker.getLatLng(), {animate: true});
    if (window.matchMedia('(max-width: 1100px)').matches) {
      panel.root.scrollIntoView({behavior: 'smooth', block: 'start'});
    }
  }

  function showHighlight(item) {
    markPanelUpdated('detail');
    selectMarker();
    panel.reset.hidden = false;
    panel.reset.textContent = `← Back to ${geography[activeStage].eyebrow.toLowerCase()}`;
    panel.title.textContent = item.title;
    panel.summary.textContent = item.text;
    panel.anecdote.textContent = item.relationship || 'Connected to the family tree.';
    panel.listLabel.textContent = 'Follow this family thread';
    panel.places.innerHTML = '';
    if (item.person?.id) {
      const person = document.createElement('a');
      person.href = `/people/${encodeURIComponent(item.person.id)}`;
      person.textContent = item.person.name;
      panel.places.appendChild(person);
    }
    if (item.sourceUrl) {
      const source = document.createElement('a');
      source.href = item.sourceUrl;
      source.target = '_blank';
      source.rel = 'noopener';
      source.textContent = `${item.sourceLabel || 'Read the historical source'} ↗`;
      panel.places.appendChild(source);
    }
    panel.method.textContent = item.status === 'Family thread'
      ? 'This note keeps historical context beside the imported family-tree record.'
      : 'This observation follows dates and places recorded in the imported family tree.';
    map.panTo([item.lat, item.lng], {animate: true});
    if (window.matchMedia('(max-width: 1100px)').matches) {
      panel.root.scrollIntoView({behavior: 'smooth', block: 'start'});
    }
  }

  function showOverview() {
    const stage = geography[activeStage];
    markPanelUpdated('overview');
    selectMarker();
    panel.reset.hidden = true;
    panel.title.textContent = stage.title;
    panel.summary.textContent = stage.summary;
    panel.anecdote.textContent = stage.anecdote || 'Every point on the map opens a different part of the family story.';
    panel.listLabel.textContent = 'Places in this chapter';
    panel.method.textContent = stage.method;
    panel.places.innerHTML = '';
    stage.items.slice(0, LIST_LIMIT).forEach(item => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `${item.name} · ${item.people}`;
      button.addEventListener('click', () => { showItem(item); syncLocation(item); });
      panel.places.appendChild(button);
    });
    const remainder = stage.items.length - LIST_LIMIT;
    if (remainder > 0) {
      const more = document.createElement('a');
      more.className = 'stage-more';
      more.href = '/places';
      more.textContent = `+${remainder} more in the atlas →`;
      panel.places.appendChild(more);
    }
  }

  function catmullRomPoints(controls, stepsPerSegment = 12) {
    const points = [];
    for (let segment = 0; segment < controls.length - 1; segment += 1) {
      const p0 = controls[Math.max(0, segment - 1)];
      const p1 = controls[segment];
      const p2 = controls[segment + 1];
      const p3 = controls[Math.min(controls.length - 1, segment + 2)];
      for (let step = 0; step < stepsPerSegment; step += 1) {
        const t = step / stepsPerSegment;
        const t2 = t * t;
        const t3 = t2 * t;
        points.push([0, 1].map(axis => .5 * (
          2 * p1[axis]
          + (-p0[axis] + p2[axis]) * t
          + (2 * p0[axis] - 5 * p1[axis] + 4 * p2[axis] - p3[axis]) * t2
          + (-p0[axis] + 3 * p1[axis] - 3 * p2[axis] + p3[axis]) * t3
        )));
      }
    }
    points.push(controls[controls.length - 1]);
    return points;
  }

  // Unevenly spaced bends make the Atlantic span read as a watercourse with
  // calm reaches and turns, rather than one mathematically perfect arc.
  function riverPoints(from, to, bendOffsets) {
    const fractions = [0, .1, .24, .43, .63, .82, 1];
    const controls = fractions.map((fraction, index) => [
      from[0] + (to[0] - from[0]) * fraction + (bendOffsets[index] || 0),
      from[1] + (to[1] - from[1]) * fraction,
    ]);
    return catmullRomPoints(controls, 18);
  }

  function tributaryPoints(from, mainPoints, attachmentIndex, phase = 0) {
    const to = mainPoints[attachmentIndex];
    const [y1, x1] = from;
    const [y2, x2] = to;
    const downstream = mainPoints[Math.min(mainPoints.length - 1, attachmentIndex + 3)];
    const tangentY = downstream[0] - y2;
    const tangentX = downstream[1] - x2;
    const c1x = x1 + (x2 - x1) * .3;
    const c2x = x2 - tangentX * 2.2;
    const c1y = y1 + (y2 - y1) * .18 + Math.sin(phase) * .8;
    const c2y = y2 - tangentY * 2.2;
    const points = [];
    for (let step = 0; step <= 36; step += 1) {
      const t = step / 36;
      const a = (1 - t) ** 3;
      const b = 3 * (1 - t) ** 2 * t;
      const c = 3 * (1 - t) * t ** 2;
      const d = t ** 3;
      const longitude = a * x1 + b * c1x + c * c2x + d * x2;
      const baseLatitude = a * y1 + b * c1y + c * c2y + d * y2;
      const meander = Math.sin(Math.PI * t) * Math.sin(2.5 * Math.PI * t + phase) * .45;
      points.push([baseLatitude + meander, longitude]);
    }
    return points;
  }

  function compactFamilyNames(names, limit = 4) {
    if (names.length <= limit) return names.join(', ');
    return `${names.slice(0, limit).join(', ')} +${names.length - limit}`;
  }

  function drawFamilyStreams(stage) {
    const streams = (stage.familyStreams || []).slice().sort((a, b) => b.people - a.people);
    arcs = [];
    origins = [];
    if (!streams.length) return;

    // One broad origin marker can feed several surname tributaries.
    const broadOrigins = new Map();
    streams.forEach(stream => {
      if (!broadOrigins.has(stream.origin)) {
        broadOrigins.set(stream.origin, {
          lat: stream.fromLat, lng: stream.fromLng, people: 0,
          familyNames: new Set(), branches: new Set(),
        });
      }
      const origin = broadOrigins.get(stream.origin);
      origin.people += stream.people;
      stream.familyNames.forEach(name => origin.familyNames.add(name));
      origin.branches.add(stream.branch);
    });

    function drawTaperedStream(points, color, startWeight, endWeight, tooltip, primary = false) {
      const hitArea = L.polyline(points, {
        color, weight: Math.max(startWeight, endWeight) + 6, opacity: 0,
        lineCap: 'round', lineJoin: 'round', interactive: true,
      }).addTo(routeLayer);
      if (tooltip) hitArea.bindTooltip(tooltip, {sticky: true, className: 'family-stream-tooltip'});

      const baseWeight = Math.min(startWeight, endWeight);
      L.polyline(points, {
        color, weight: baseWeight + 1.7, opacity: primary ? .25 : .17,
        lineCap: 'round', lineJoin: 'round', interactive: false,
      }).addTo(routeLayer);
      L.polyline(points, {
        color, weight: baseWeight, opacity: .96,
        lineCap: 'round', lineJoin: 'round', interactive: false,
      }).addTo(routeLayer);

      // Flat-ended, closely spaced reaches add the gradual widening. The solid
      // channel beneath them prevents antialiasing seams from reading as dots.
      const sectionCount = 28;
      for (let index = 0; index < sectionCount; index += 1) {
        const start = Math.floor(index * (points.length - 1) / sectionCount);
        const end = Math.min(
          points.length,
          Math.ceil((index + 1) * (points.length - 1) / sectionCount) + 1,
        );
        const progress = (index + .5) / sectionCount;
        const eased = progress * progress * (3 - 2 * progress);
        const weight = startWeight + (endWeight - startWeight) * eased;
        const section = points.slice(start, end);
        L.polyline(section, {
          color, weight: weight + (primary ? 2 : 1.5), opacity: primary ? .24 : .16,
          lineCap: 'butt', lineJoin: 'round', interactive: false,
        }).addTo(routeLayer);
        L.polyline(section, {
          color, weight, opacity: .96,
          lineCap: 'butt', lineJoin: 'round', interactive: false,
        }).addTo(routeLayer);
      }
      arcs.push({points, people: Math.max(startWeight, endWeight)});
    }

    // Branches are styled by slot (their order in the site profile), never by
    // name. Junctions, where each branch's tributaries gather before crossing,
    // come from the profile; the rest are small offsets that keep branches
    // landing in the same region legible.
    const branchJunctions = new Map((stage.branches || []).map(branch => [branch.slot, branch.junction]));
    const branchArrivalOffsets = [[-.35, -.45], [0, 0], [0, 0], [.1, .65]];
    const branchBends = [
      {offsets: [0, -1.2, .7, -1.1, 1.25, -.45, 0], phase: .2},
      {offsets: [0, 1.1, -1.45, .85, -1.05, .65, 0], phase: 1.1},
      {offsets: [0, -.75, 1.35, -1.05, .75, -.4, 0], phase: 2.2},
      {offsets: [0, .85, -1.05, 1.5, -.75, .55, 0], phase: 3.1},
    ];
    const branchLabelDirections = ['left', 'left', 'right', 'right'];
    const byBranch = new Map();
    streams.forEach(stream => {
      if (!byBranch.has(stream.branch)) byBranch.set(stream.branch, []);
      byBranch.get(stream.branch).push(stream);
    });

    byBranch.forEach((branchStreams, branch) => {
      const slot = branchStreams[0]?.slot ?? 0;
      const color = familyStreamColors[slot % familyStreamColors.length] || token('--muted', '#5d6e70');
      const junction = branchJunctions.get(slot) || [45, -30];
      const originGroups = new Map();
      const destinationGroups = new Map();
      const allNames = new Set();
      let totalPeople = 0;
      branchStreams.forEach(stream => {
        totalPeople += stream.people;
        stream.familyNames.forEach(name => allNames.add(name));
        const origin = originGroups.get(stream.origin) || {
          lat: stream.fromLat, lng: stream.fromLng, people: 0, names: new Set(),
        };
        origin.people += stream.people;
        stream.familyNames.forEach(name => origin.names.add(name));
        originGroups.set(stream.origin, origin);
        const destination = destinationGroups.get(stream.destination) || {
          lat: stream.toLat, lng: stream.toLng, people: 0, names: new Set(),
        };
        destination.people += stream.people;
        stream.familyNames.forEach(name => destination.names.add(name));
        destinationGroups.set(stream.destination, destination);
      });

      const destinations = [...destinationGroups.entries()].sort((a, b) => b[1].people - a[1].people);
      const primaryDestination = destinations[0]?.[1] || {lat: 38, lng: -88};
      const arrivalOffset = branchArrivalOffsets[slot] || [0, 0];
      const hub = [
        primaryDestination.lat + arrivalOffset[0],
        primaryDestination.lng + arrivalOffset[1],
      ];
      const bends = branchBends[slot] || {offsets: [0, 1, -1, .7, -.7, .4, 0], phase: 0};
      const primaryPoints = riverPoints(junction, hub, bends.offsets);
      const primaryWeight = Math.min(9, 5 + Math.sqrt(totalPeople) * .72);
      const primaryStartWeight = primaryWeight * .52;
      const originEntries = [...originGroups.entries()].sort((a, b) => b[1].lng - a[1].lng);
      originEntries.forEach(([originName, origin], index) => {
        const names = [...origin.names].sort();
        const spread = originEntries.length > 1 ? index / (originEntries.length - 1) : 0;
        const attachmentIndex = Math.round(spread * .16 * (primaryPoints.length - 1));
        const tributary = tributaryPoints(
          [origin.lat, origin.lng], primaryPoints, attachmentIndex, bends.phase + index * .85,
        );
        const attachmentProgress = attachmentIndex / (primaryPoints.length - 1);
        const attachmentEase = attachmentProgress ** 2 * (3 - 2 * attachmentProgress);
        const attachmentWeight = primaryStartWeight
          + (primaryWeight - primaryStartWeight) * attachmentEase;
        drawTaperedStream(
          tributary, color,
          Math.min(2.4, .75 + Math.sqrt(origin.people) * .26), attachmentWeight,
          `<strong>${escapeHtml(branch)}</strong><span>${escapeHtml(compactFamilyNames(names))}</span><span>General origin: ${escapeHtml(originName)}</span>`,
        );
      });

      const names = [...allNames].sort();
      drawTaperedStream(
        primaryPoints, color, primaryStartWeight, primaryWeight,
        `<strong>${escapeHtml(branch)}</strong><span>${escapeHtml(compactFamilyNames(names, 7))}</span><span>${totalPeople} recorded family connections</span>`,
        true,
      );

      destinations.forEach(([destinationName, destination], index) => {
        const distance = Math.hypot(destination.lat - hub[0], destination.lng - hub[1]);
        if (distance < 1.2) return;
        const destinationGuide = riverPoints(hub, [destination.lat, destination.lng], [0, .35, -.3, .2, -.2, .1, 0]);
        drawTaperedStream(
          destinationGuide, color, primaryWeight * .82,
          Math.min(3, .9 + Math.sqrt(destination.people) * .34),
          `<strong>${escapeHtml(branch)}</strong><span>${escapeHtml(compactFamilyNames([...destination.names].sort()))}</span><span>General U.S. foothold: ${escapeHtml(destinationName)}</span>`,
        );
      });

      L.circleMarker(hub, {
        radius: 6, color: token('--surface', '#f5f5f0'), weight: 2, fillColor: color, fillOpacity: 1,
      }).addTo(routeLayer).bindTooltip(branch.replace(' branch', ''), {
        permanent: true, direction: branchLabelDirections[slot] || 'right',
        offset: [(branchLabelDirections[slot] === 'left' ? -7 : 7), 0],
        className: 'family-stream-branch-label',
      });
    });

    broadOrigins.forEach((info, name) => {
      const familyNames = [...info.familyNames].sort();
      const marker = L.circleMarker([info.lat, info.lng], {
        radius: Math.max(6, Math.min(12, 4 + Math.sqrt(info.people) * 1.4)),
        color: token('--surface', '#f5f5f0'), weight: 2.5, fillColor: colors.origins, fillOpacity: .98,
      }).addTo(routeLayer);
      marker.bindTooltip(
        `<strong>${escapeHtml(name)}</strong><span>${escapeHtml(compactFamilyNames(familyNames, 6))}</span>`,
        {sticky: true, className: 'family-stream-tooltip'},
      );
      origins.push({marker, text: `${name} · ${familyNames.length} family name${familyNames.length === 1 ? '' : 's'}`});
    });
  }

  function drawStoryFlags(stage) {
    flags = [];
    (stage.highlights || []).forEach(item => {
      const marker = L.marker([item.lat, item.lng], {
        icon: L.divIcon({
          className: 'home-story-flag',
          html: '<i aria-hidden="true"></i>',
          iconSize: [22, 30],
          iconAnchor: [4, 28],
        }),
        title: item.mapLabel,
        riseOnHover: true,
      }).addTo(storyLayer);
      marker.on('click', () => showHighlight(item));
      flags.push({marker, text: item.mapLabel});
    });
  }

  function renderStage(stageName, animate = true) {
    activeStage = stageName;
    markerLayer.clearLayers();
    routeLayer.clearLayers();
    storyLayer.clearLayers();
    countLayer.clearLayers();
    markerByName = new Map();
    const stage = geography[stageName];
    const color = colors[stageName];
    panel.streamLegend.hidden = !(stage.familyStreams || []).length;
    drawFamilyStreams(stage);
    drawStoryFlags(stage);

    // Show the places that carry the story; the long tail stays one click away
    // on the atlas rather than crowding the map with two-person dots.
    const compact = map.getSize().x < 900;
    const shown = stage.items.slice(0, compact ? 6 : MARKER_LIMIT);
    // In the symbolic stream chapter, branch hubs and origin tributaries are
    // the visual anchors. Generic place-count rings add a second, unclear
    // symbol system, so reserve those markers for the place-focused chapters.
    const mappedItems = stage.familyStreams?.length ? [] : shown;
    placed = [];
    mappedItems.forEach((item, rank) => {
      const marker = L.marker([item.lat, item.lng], {
        icon: markerIcon(item, color, rank),
        title: item.name,
        riseOnHover: true,
      }).addTo(markerLayer);
      marker.on('click', () => { showItem(item); syncLocation(item); });
      markerByName.set(item.name, marker);
      placed.push({marker, item});
    });

    frameStage(mappedItems, stage, animate);
    document.querySelectorAll('[data-stage]').forEach(button => {
      const selected = button.dataset.stage === stageName;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', String(selected));
      button.disabled = false;
    });
    showOverview();
    window.setTimeout(layoutLabels, animate ? 360 : 40);
  }

  async function start() {
    try {
      const [countries, stageData] = await Promise.all([
        fetch('/static/data/ne_110m_admin_0_countries.geojson').then(response => response.json()),
        fetch('/api/geography').then(response => response.json()),
      ]);
      geography = stageData;
      // The home-region outline is optional and named by the site profile.
      const outlineUrl = geography.homesteads?.center?.outline;
      const homeOutline = outlineUrl
        ? await fetch(outlineUrl).then(response => response.ok ? response.json() : null).catch(() => null)
        : null;
      L.geoJSON(countries, {
        interactive: false,
        style: {color: token('--water', '#4a6e86'), weight: .75, fillColor: token('--juniper-soft', '#d9e7df'), fillOpacity: .96},
      }).addTo(map);
      if (homeOutline) {
        L.geoJSON(homeOutline, {
          interactive: false,
          style: {color: token('--ink', '#1b2a2e'), weight: 2, fillColor: token('--juniper', '#2f6152'), fillOpacity: .32},
        }).addTo(map);
      }
      [20, 40, 60].forEach(lat => L.polyline([[lat, -130], [lat, 30]], {
        color: token('--surface', '#f5f5f0'), weight: .55, opacity: .35, interactive: false,
      }).addTo(map));
      [-100, -50, 0].forEach(lng => L.polyline([[10, lng], [70, lng]], {
        color: token('--surface', '#f5f5f0'), weight: .55, opacity: .35, interactive: false,
      }).addTo(map));
      countryLayerToBack();
      const query = new URLSearchParams(window.location.search);
      const requestedStage = query.get('stage');
      renderStage(geography[requestedStage] ? requestedStage : 'gateways', false);
      const requestedPlace = query.get('place');
      const selected = requestedPlace && geography[activeStage].items.find(item => item.slug === requestedPlace);
      if (selected) showItem(selected);

    } catch (error) {
      panel.summary.textContent = 'The map is unavailable. Use Browse all places to explore family geography, or search for a relative below.';
      panel.method.textContent = 'Browse the place pages to explore family geography.';
    }
  }

  function countryLayerToBack() {
    // Leaflet renders GeoJSON before markers because it was added first; this named
    // function documents the intended layer order for future map additions.
  }

  map.on('moveend zoomend', layoutLabels);

  document.querySelectorAll('[data-stage]').forEach(button => {
    button.addEventListener('click', () => {
      if (!geography) return;
      renderStage(button.dataset.stage);
      syncLocation();
    });
  });
  panel.reset.addEventListener('click', () => { showOverview(); syncLocation(); });
  start();
})();
