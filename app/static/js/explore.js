(() => {
  const explorer = document.querySelector('.explorer');
  if (!explorer) return;
  const params = new URLSearchParams(window.location.search);
  let root = explorer.dataset.root;
  const defaultRoot = explorer.dataset.defaultRoot;
  let direction = params.get('direction') === 'descendants' ? 'descendants' : 'ancestors';
  let scope = ['2', 'all', 'fit'].includes(params.get('scope')) ? params.get('scope') : 'fit';
  let generations = scope === '2' ? 2 : 10;
  let mapLoaded = false;
  let currentRootName = '';
  let treeRequest = 0;
  const treeTrail = [];
  const collapsedNodes = new Set();
  let initializeFittedView = scope === 'fit';

  const mobileControlToggle = document.getElementById('mobile-control-toggle');
  mobileControlToggle?.addEventListener('click', () => {
    const sidebar = mobileControlToggle.closest('.explore-sidebar');
    const open = !sidebar.classList.contains('controls-open');
    sidebar.classList.toggle('controls-open', open);
    mobileControlToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  });

  // Mirror explorer state into the address bar so a view built here can be
  // bookmarked or sent to a relative.
  function syncUrl() {
    const next = new URLSearchParams();
    next.set('root', root);
    if (direction !== 'ancestors') next.set('direction', direction);
    next.set('scope', scope);
    if (document.getElementById('map-panel').classList.contains('active')) next.set('view', 'map');
    history.replaceState(null, '', `${window.location.pathname}?${next}`);
  }

  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const theme = getComputedStyle(document.documentElement);
  const themeColor = (name, fallback) => theme.getPropertyValue(name).trim() || fallback;
  const palette = {
    navy: themeColor('--navy', '#173f6b'),
    blue: themeColor('--blue', '#286fa8'),
    yellow: themeColor('--yellow', '#f2c84b')
  };

  async function loadTree() {
    const request = ++treeRequest;
    const status = document.getElementById('tree-status');
    status.style.display = 'block';
    status.textContent = 'Growing this branch…';
    try {
      const response = await fetch(`/api/tree?root=${encodeURIComponent(root)}&direction=${direction}&generations=${generations}`);
      if (!response.ok) throw new Error('Tree unavailable');
      const data = await response.json();
      if (request !== treeRequest) return;
      root = data.root;
      applyDepth(data);
      updateRootContext(data);
      updateDirectionAvailability(data);
      renderContinuation(data);
      renderTrail();
      prepareFittedView(data);
      renderTree(data);
      status.style.display = 'none';
      syncUrl();
    } catch (error) {
      if (request === treeRequest) status.textContent = 'The tree could not be loaded.';
    }
  }

  function applyDepth(data) {
    const hint = document.getElementById('generation-hint');
    const select = document.getElementById('tree-depth');
    const available = Number(data.availableDepth) || 0;
    generations = scope === '2' ? 2 : 10;
    if (select) {
      select.value = scope;
      [...select.options].forEach(option => {
        option.disabled = option.value === '2' && available < 1;
      });
    }
    if (!hint) return;
    hint.textContent = !available
      ? `No ${direction === 'ancestors' ? 'earlier' : 'later'} public generations are recorded from this person.`
      : scope === 'fit'
        ? `Fitted overview of ${available} available family ${available === 1 ? 'step' : 'steps'}. Show or hide family on a card to open and close lines.`
        : scope === 'all'
        ? `Showing the whole public branch: ${available} ${available === 1 ? 'step' : 'steps'} from this person.`
        : `Showing ${Math.min(2, available)} of ${available} available family steps.`;
  }

  function updateRootContext(data) {
    const name = document.getElementById('tree-root-name');
    const reason = document.getElementById('tree-root-reason');
    const record = document.getElementById('tree-root-record');
    currentRootName = data.rootPerson?.name || 'Selected relative';
    const person = data.rootPerson || {};
    const summary = document.getElementById('tree-person-summary');
    const facts = [person.years ? `${person.years}.` : '', person.birthPlace ? `Birth recorded in ${person.birthPlace}.` : '', person.deathPlace ? `Death recorded in ${person.deathPlace}.` : ''].filter(Boolean);
    const parents = (data.rootConnections?.earlier || []).map(relative => relative.name);
    const detail = [facts.join(' ') || 'A starting point for exploring the public family tree.',
      parents.length ? `Parents in the tree: ${parents.join(' and ')}.` : ''].filter(Boolean).join(' ');
    summary.innerHTML = `<p class="control-label">In focus</p><h2>${escapeHtml(currentRootName)}</h2><p>${escapeHtml(detail)}</p>${data.rootRecordAvailable ? `<a href="/people/${encodeURIComponent(person.id)}">Read the person’s record &rarr;</a>` : ''}`;
    if (name) name.textContent = currentRootName;
    const mobileSummary = document.getElementById('mobile-control-summary');
    if (mobileSummary) mobileSummary.textContent = `${currentRootName} · ${direction === 'ancestors' ? 'Earlier family' : 'Later family'}`;
    if (record && data.rootPerson?.id) {
      record.href = `/people/${encodeURIComponent(data.rootPerson.id)}`;
      record.hidden = data.rootRecordAvailable === false;
    }
    const branchStart = document.getElementById('branch-start');
    if (branchStart) branchStart.value = [...branchStart.options].some(option => option.value === data.root) ? data.root : '';
    if (!reason) return;
    if (data.root === defaultRoot) {
      reason.textContent = direction === 'ancestors'
        ? 'A familiar grandparent-generation anchor, opening this branch backward in time.'
        : 'A familiar grandparent-generation anchor, showing the public family that follows.';
    } else {
      reason.textContent = direction === 'ancestors'
        ? 'The tree is centered here and moving toward parents and earlier generations.'
        : 'The tree is centered here and moving toward children and later generations.';
    }
  }

  function updateDirectionAvailability(data) {
    const connections = data.rootConnections || {};
    document.querySelectorAll('[data-direction]').forEach(button => {
      const key = button.dataset.direction === 'ancestors' ? 'earlier' : 'later';
      const available = (connections[key] || []).length > 0;
      button.disabled = !available && button.dataset.direction !== direction;
    });
  }

  function renderContinuation(data) {
    const container = document.getElementById('tree-continuation');
    if (!container) return;
    const connections = data.rootConnections || {};
    const opposite = direction === 'ancestors' ? 'descendants' : 'ancestors';
    const relatives = connections[opposite === 'ancestors' ? 'earlier' : 'later'] || [];
    if (!relatives.length) {
      container.innerHTML = Number(data.availableDepth)
        ? ''
        : '<p>No additional public family is recorded immediately before or after this person.</p>';
      return;
    }
    const label = opposite === 'ancestors' ? 'Continue to earlier family' : 'Continue to later family';
    const message = Number(data.availableDepth)
      ? 'You can also turn around from this person.'
      : 'This path ends in this direction, but the family continues the other way.';
    container.innerHTML = `<p>${message}</p><button type="button" data-continue-direction="${opposite}"><span>${label}</span><span aria-hidden="true">→</span></button>`;
    container.querySelector('button').addEventListener('click', () => {
      setDirection(opposite);
      loadTree();
    });
  }

  function renderTrail() {
    const back = document.getElementById('tree-back');
    const list = document.getElementById('tree-trail');
    if (back) back.disabled = treeTrail.length === 0;
    const canvasBack = document.getElementById('tree-canvas-back');
    if (canvasBack) {
      canvasBack.disabled = treeTrail.length === 0;
      canvasBack.textContent = treeTrail.length ? `\u2190 Back to ${treeTrail[treeTrail.length - 1].name}` : '\u2190 Back to previous person';
    }
    if (list) list.innerHTML = treeTrail.slice(-3).map(item => `<li title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</li>`).join('');
  }

  function navigateTo(personId, personName) {
    if (!personId || personId === root) return;
    treeTrail.push({root, name: currentRootName, direction, generations, scope});
    root = personId;
    currentRootName = personName || '';
    collapsedNodes.clear();
    initializeFittedView = scope === 'fit';
    loadTree();
  }

  function navigateBack() {
    const previous = treeTrail.pop();
    if (!previous) return;
    root = previous.root;
    direction = previous.direction;
    generations = previous.generations;
    scope = previous.scope || 'fit';
    collapsedNodes.clear();
    initializeFittedView = scope === 'fit';
    setDirection(direction);
    loadTree();
  }

  function outwardMap(data) {
    const generationsById = new Map(data.nodes.map(node => [node.id, node.generation]));
    const outward = new Map(data.nodes.map(node => [node.id, []]));
    data.links.forEach(link => {
      const sourceGeneration = generationsById.get(link.source);
      const targetGeneration = generationsById.get(link.target);
      if (sourceGeneration == null || targetGeneration == null || sourceGeneration === targetGeneration) return;
      const inner = sourceGeneration < targetGeneration ? link.source : link.target;
      const outer = inner === link.source ? link.target : link.source;
      outward.get(inner)?.push(outer);
    });
    return outward;
  }

  function prepareFittedView(data) {
    if (!initializeFittedView || scope !== 'fit') return;
    collapsedNodes.clear();
    const outward = outwardMap(data);
    const frontier = Math.max(1, Math.min(3, Math.floor((document.getElementById('tree-canvas').clientWidth - 56) / 288) - 1));
    data.nodes.forEach(node => {
      if (node.generation === frontier && outward.get(node.id)?.length) collapsedNodes.add(node.id);
    });
    initializeFittedView = false;
  }

  function visibleTreeData(data) {
    if (!collapsedNodes.size) return data;
    const outward = outwardMap(data);
    const sameGeneration = new Map(data.nodes.map(node => [node.id, []]));
    const generationsById = new Map(data.nodes.map(node => [node.id, node.generation]));
    data.links.forEach(link => {
      if (generationsById.get(link.source) === generationsById.get(link.target)) {
        sameGeneration.get(link.source)?.push(link.target);
        sameGeneration.get(link.target)?.push(link.source);
      }
    });
    const hidden = new Set();
    const queue = [...collapsedNodes].flatMap(id => outward.get(id) || []);
    while (queue.length) {
      const id = queue.shift();
      if (hidden.has(id)) continue;
      hidden.add(id);
      queue.push(...(outward.get(id) || []), ...(sameGeneration.get(id) || []));
    }
    return {
      ...data,
      nodes: data.nodes.filter(node => !hidden.has(node.id)),
      links: data.links.filter(link => !hidden.has(link.source) && !hidden.has(link.target))
    };
  }

  function generationLabel(generation) {
    if (generation === 0) return 'Starting person';
    if (direction === 'descendants') {
      if (generation === 1) return 'Children';
      if (generation === 2) return 'Grandchildren';
      if (generation === 3) return 'Great-grandchildren';
      return `${generation - 2}× great-grandchildren`;
    }
    if (generation === 1) return 'Parents';
    if (generation === 2) return 'Grandparents';
    if (generation === 3) return 'Great-grandparents';
    return `${generation - 2}× great-grandparents`;
  }

  function renderTree(data) {
    const sourceData = data;
    const fullOutward = outwardMap(sourceData);
    data = visibleTreeData(sourceData);
    const canvas = document.getElementById('tree-canvas');
    const groups = new Map();
    data.nodes.forEach(node => {
      if (!groups.has(node.generation)) groups.set(node.generation, []);
      groups.get(node.generation).push(node);
    });
    const nodeW = 240, nodeH = 118, colGap = 48, rowGap = 20, pad = 28;
    const scaleFor = () => 1;
    const orderedGroups = [...groups.entries()].sort((a,b) => a[0]-b[0]);
    const columnWidths = orderedGroups.map(([generation]) => nodeW * scaleFor(generation));
    const width = Math.max(canvas.clientWidth, pad * 2 + columnWidths.reduce((sum, value) => sum + value + colGap, 0));
    const heightNeeded = orderedGroups.map(([generation, nodes]) => nodes.length * (nodeH + rowGap) * scaleFor(generation));
    // A two-card branch in a full-height canvas reads as a broken page, especially
    // on a phone. Let the canvas shrink toward its content, keeping enough room to
    // stay recognisably a workspace.
    canvas.style.height = '';
    const contentHeight = pad * 2 + Math.max(...heightNeeded, 1);
    if (contentHeight < canvas.clientHeight) {
      canvas.style.height = `${Math.max(320, contentHeight)}px`;
    }
    const height = Math.max(canvas.clientHeight, contentHeight);
    const positions = new Map();
    let columnX = pad;
    orderedGroups.forEach(([generation, nodes], col) => {
      const scale = scaleFor(generation), scaledW = nodeW * scale, scaledH = nodeH * scale, scaledGap = rowGap * scale;
      // Keep each household beside the relative connecting it to the previous column.
      const innerPosition = node => {
        const connected = data.links.flatMap(link => link.source === node.id ? [link.target] : link.target === node.id ? [link.source] : []);
        const ys = connected.map(id => positions.get(id)).filter(position => position && position.generation < generation).map(position => position.y + position.h / 2);
        return ys.length ? ys.reduce((sum, y) => sum + y, 0) / ys.length : Infinity;
      };
      nodes.sort((a,b) => innerPosition(a) - innerPosition(b) || (a.years || '').localeCompare(b.years || '') || a.name.localeCompare(b.name));
      const groupHeight = nodes.length * scaledH + (nodes.length - 1) * scaledGap;
      nodes.forEach((node, row) => positions.set(node.id, {
        x: columnX, y: (height - groupHeight) / 2 + row * (scaledH + scaledGap), w: scaledW, h: scaledH, scale, generation
      }));
      columnX += scaledW + colGap;
    });
    const labelsHtml = orderedGroups.map(([generation]) => {
      const first = [...positions.values()].find(position => position.generation === generation);
      return first ? `<span style="left:${first.x}px">${escapeHtml(generationLabel(generation))}</span>` : '';
    }).join('');
    const linkSvg = data.links.map(link => {
      const a = positions.get(link.source), b = positions.get(link.target);
      if (!a || !b) return '';
      const ax = a.x + a.w, ay = a.y + a.h/2, bx = b.x, by = b.y + b.h/2;
      if (link.kind === 'spouse' && Math.abs(a.x-b.x) < 5) {
        return `<path class="tree-link spouse" d="M${a.x+a.w/2},${a.y+a.h} L${b.x+b.w/2},${b.y}"/>`;
      }
      const mid = (ax+bx)/2;
      return `<path class="tree-link ${link.kind}" d="M${ax},${ay} C${mid},${ay} ${mid},${by} ${bx},${by}"/>`;
    }).join('');
    const nodesSvg = data.nodes.map(node => {
      const p = positions.get(node.id);
      const place = node.birthPlace ? node.birthPlace.split(',')[0] : 'Place unknown';
      const indicators = `${node.researchReview ? '<circle class="node-research-review" cx="222" cy="46" r="5"><title>Some dates or connections need verification</title></circle>' : ''}${node.hasStory ? '<text class="node-story-marker" x="213" y="70"><title>Featured in a family story</title>\u25c6</text>' : ''}`;
      const shorten = (value, limit) => value.length > limit ? value.slice(0, limit - 1) + '\u2026' : value;
      return `<g class="tree-node generation-${p.generation} ${node.id === data.root ? 'root' : ''}" data-id="${escapeHtml(node.id)}" transform="translate(${p.x} ${p.y})"><rect class="node-card" width="${nodeW}" height="${fullOutward.get(node.id)?.length ? nodeH : 82}"/><g class="node-focus" tabindex="0" role="button" aria-label="Center the tree on ${escapeHtml(node.name)}"><title>${escapeHtml(node.name)}: click to focus</title><rect class="node-focus-hit" width="${nodeW}" height="78"/><text class="node-name" x="14" y="25">${escapeHtml(shorten(node.name, 27))}</text><text class="node-meta" x="14" y="48">${escapeHtml(node.years)}</text><text class="node-meta" x="14" y="69">${escapeHtml(shorten(place, 26))}</text>${indicators}</g></g>`;
    }).join('');
    canvas.innerHTML = `<div class="tree-pan-hint">Select a name to focus. Drag the background to explore.</div><div class="tree-column-headings" style="width:${width}px">${labelsHtml}</div><svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" aria-label="Interactive family tree"><g>${linkSvg}${nodesSvg}</g></svg>`;
    const branchSurname = (sourceData.rootPerson?.surname || '').toLowerCase();
    const branchIds = new Set(sourceData.nodes.filter(node => (node.surname || '').toLowerCase() === branchSurname).map(node => node.id));
    canvas.querySelectorAll('.tree-link').forEach((path, index) => {
      const link = data.links[index];
      if (link && branchIds.has(link.source) && branchIds.has(link.target)) path.classList.add('branch-line');
    });
    const rootPosition = positions.get(data.root);
    if (rootPosition) {
      requestAnimationFrame(() => {
        canvas.scrollTop = Math.max(0, rootPosition.y - canvas.clientHeight / 2 + rootPosition.h / 2);
        canvas.scrollLeft = 0;
      });
    }
    canvas.querySelectorAll('.tree-node').forEach(node => {
      const person = data.nodes.find(item => item.id === node.dataset.id);
      if (branchIds.has(node.dataset.id)) node.classList.add('branch-line');
      const focus = node.querySelector('.node-focus');
      const recenter = () => {
        navigateTo(node.dataset.id, person?.name);
      };
      focus.addEventListener('click', recenter);
      focus.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          recenter();
        }
      });
      if (fullOutward.get(node.dataset.id)?.length) {
        const namespace = 'http://www.w3.org/2000/svg';
        const toggle = document.createElementNS(namespace, 'g');
        toggle.classList.add('node-toggle');
        toggle.setAttribute('tabindex', '0');
        toggle.setAttribute('role', 'button');
        const closed = collapsedNodes.has(node.dataset.id);
        const toggleLabel = `${closed ? 'Open' : 'Close'} the family line beyond ${person?.name || 'this relative'}`;
        toggle.setAttribute('aria-label', toggleLabel);
        const title = document.createElementNS(namespace, 'title');
        title.textContent = toggleLabel;
        const circle = document.createElementNS(namespace, 'rect');
        circle.setAttribute('x', '13'); circle.setAttribute('y', '82'); circle.setAttribute('width', '106'); circle.setAttribute('height', '24');
        circle.setAttribute('rx', '3');
        toggle.setAttribute('aria-expanded', String(!closed));
        const symbol = document.createElementNS(namespace, 'text');
        symbol.setAttribute('x', '66'); symbol.setAttribute('y', '98'); symbol.textContent = closed ? '+ Expand' : '\u2212 Collapse';
        toggle.append(title, circle, symbol);
        const toggleBranch = event => {
          event.stopPropagation();
          if (collapsedNodes.has(node.dataset.id)) collapsedNodes.delete(node.dataset.id);
          else collapsedNodes.add(node.dataset.id);
          const before = node.getBoundingClientRect();
          renderTree(sourceData);
          requestAnimationFrame(() => {
            const updated = [...canvas.querySelectorAll('.tree-node')].find(item => item.dataset.id === node.dataset.id);
            const after = updated.getBoundingClientRect();
            canvas.scrollTop += after.top - before.top;
            canvas.scrollLeft += after.left - before.left;
            updated.querySelector('.node-toggle')?.focus({preventScroll: true});
          });
        };
        toggle.addEventListener('click', toggleBranch);
        toggle.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggleBranch(event); }
        });
        node.append(toggle);
      }
    });
  }

  async function loadMap() {
    if (mapLoaded) return;
    mapLoaded = true;
    const element = document.getElementById('family-map');
    if (!window.L) { element.innerHTML = '<div class="viz-status">Map tiles are unavailable, but the family tree still works.</div>'; return; }
    const map = L.map(element, {scrollWheelZoom: false, worldCopyJump: true}).setView([42, -22], 3);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 18, attribution: '&copy; OpenStreetMap contributors'}).addTo(map);
    const geography = await fetch('/api/geography').then(r => r.json()).catch(() => null);
    const center = geography?.homesteads?.center;
    if (center && center.lat !== null && center.lng !== null) {
      const home = [center.lat, center.lng];
      (geography.origins?.items || []).slice(0, 8).forEach(item => {
        const origin = [item.lat, item.lng];
        const midpoint = [(origin[0] + home[0]) / 2 + 9, (origin[1] + home[1]) / 2];
        L.polyline([origin, midpoint, home], {color:palette.yellow,weight:1.5,opacity:.72,dashArray:'5 7',interactive:false}).addTo(map);
      });
    }
    const places = await fetch('/api/places').then(r => r.json());
    places.forEach(place => {
      const radius = Math.max(5, Math.min(25, 4 + Math.sqrt(place.count) * 2.2));
      L.circleMarker([place.lat, place.lng], {radius, color:palette.yellow,weight:2,fillColor:palette.navy,fillOpacity:.78})
        .bindPopup(`<strong>${escapeHtml(place.name)}</strong><span>${place.count} events · ${place.people} people</span><span>${place.firstYear || '?'}–${place.lastYear || '?'}</span><a href="/places/${encodeURIComponent(place.slug)}">Open this place →</a>`).addTo(map);
    });
    setTimeout(() => map.invalidateSize(), 50);
  }

  function setDirection(value) {
    if (direction !== value) {
      collapsedNodes.clear();
      initializeFittedView = scope === 'fit';
    }
    direction = value;
    document.querySelectorAll('[data-direction]').forEach(b => {
      const on = b.dataset.direction === value;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  function setView(name) {
    document.querySelectorAll('[data-view]').forEach(b => {
      const on = b.dataset.view === name;
      b.classList.toggle('active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    document.querySelectorAll('.view-panel').forEach(panel => panel.classList.toggle('active', panel.id === name));
    if (name === 'map-panel') loadMap();
    syncUrl();
  }

  document.querySelectorAll('[data-direction]').forEach(button => button.addEventListener('click', () => {
    setDirection(button.dataset.direction);
    loadTree();
  }));
  document.getElementById('tree-depth')?.addEventListener('change', event => {
    scope = event.target.value;
    generations = scope === '2' ? 2 : 10;
    collapsedNodes.clear();
    initializeFittedView = scope === 'fit';
    loadTree();
  });
  document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
  const search = document.getElementById('person-search'), results = document.getElementById('search-results');
  let searchTimer;
  search.addEventListener('input', () => {
    clearTimeout(searchTimer);
    if (search.value.trim().length < 2) { results.classList.remove('open'); return; }
    searchTimer = setTimeout(async () => {
      const people = await fetch(`/api/search?q=${encodeURIComponent(search.value)}&surnames=0`).then(r => r.json());
      results.innerHTML = people.map(p => `<button data-id="${escapeHtml(p.id)}"><span>${escapeHtml(p.name)}</span><small>${p.formalName && p.formalName !== p.name ? escapeHtml(p.formalName) + " · " : ""}${escapeHtml(p.years)} · ${escapeHtml(p.birthPlace)}</small></button>`).join('') || '<button disabled>No matching relatives</button>';
      results.classList.add('open');
      results.querySelectorAll('[data-id]').forEach(button => button.addEventListener('click', () => { const name = button.querySelector('span').textContent; search.value = name; results.classList.remove('open'); navigateTo(button.dataset.id, name); }));
    }, 220);
  });
  document.addEventListener('click', event => { if (!event.target.closest('.search-box')) results.classList.remove('open'); });
  document.getElementById('tree-back')?.addEventListener('click', navigateBack);
  document.getElementById('tree-canvas-back')?.addEventListener('click', navigateBack);
  document.getElementById('tree-reset')?.addEventListener('click', () => {
    navigateTo(defaultRoot, 'Starting person');
  });
  document.getElementById('branch-start')?.addEventListener('change', event => {
    const option = event.target.selectedOptions[0];
    treeTrail.length = 0;
    root = event.target.value;
    currentRootName = option?.dataset.name || '';
    scope = 'fit';
    generations = 10;
    collapsedNodes.clear();
    initializeFittedView = true;
    setDirection('ancestors');
    loadTree();
  });

  const panCanvas = document.getElementById('tree-canvas');
  let pan = null;
  panCanvas.addEventListener('pointerdown', event => {
    if (event.button !== 0 || event.target.closest('.node-focus, .node-toggle')) return;
    pan = {x: event.clientX, y: event.clientY, left: panCanvas.scrollLeft, top: panCanvas.scrollTop};
    panCanvas.setPointerCapture(event.pointerId);
    panCanvas.classList.add('panning');
    event.preventDefault();
  });
  panCanvas.addEventListener('pointermove', event => {
    if (!pan) return;
    panCanvas.scrollLeft = pan.left - (event.clientX - pan.x);
    panCanvas.scrollTop = pan.top - (event.clientY - pan.y);
  });
  const endPan = () => { pan = null; panCanvas.classList.remove('panning'); };
  panCanvas.addEventListener('pointerup', endPan);
  panCanvas.addEventListener('pointercancel', endPan);
  panCanvas.addEventListener('lostpointercapture', endPan);
  setDirection(direction);
  loadTree();
  if (params.get('view') === 'map' || window.location.hash === '#map-panel') {
    setView('map-panel');
  }
})();
