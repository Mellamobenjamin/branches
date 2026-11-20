(() => {
  const element = document.getElementById('place-map');
  if (!element || !window.L) return;
  const theme = getComputedStyle(document.documentElement);
  const color = (name, fallback) => theme.getPropertyValue(name).trim() || fallback;
  const palette = {
    yellow: color('--yellow', '#f2c84b'),
    land: color('--map-land', '#d9e7ec')
  };
  const point = [Number(element.dataset.lat), Number(element.dataset.lng)];
  const map = L.map(element, {scrollWheelZoom: false, attributionControl: false, zoomControl: false}).setView(point, 7);
  fetch('/static/data/ne_110m_admin_0_countries.geojson')
    .then(response => response.json())
    .then(data => L.geoJSON(data, {
      interactive: false,
      style: {color: '#82aeca', weight: .6, fillColor: palette.land, fillOpacity: .94}
    }).addTo(map));
  L.circleMarker(point, {radius: 10, color: '#fff', weight: 3, fillColor: palette.yellow, fillOpacity: 1})
    .addTo(map)
    .bindTooltip(element.dataset.name, {permanent: true, direction: 'right'});
})();
