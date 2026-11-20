(() => {
  const element = document.getElementById('person-map');
  if (!element || !window.L) return;
  const theme = getComputedStyle(document.documentElement);
  const color = (name, fallback) => theme.getPropertyValue(name).trim() || fallback;
  const palette = {
    navy: color('--navy', '#173f6b'),
    blue: color('--blue', '#286fa8'),
    yellow: color('--yellow', '#f2c84b'),
    land: color('--map-land', '#d9e7ec')
  };
  const points = JSON.parse(element.dataset.points || '[]');
  const map = L.map(element, {scrollWheelZoom: false, attributionControl: false});
  fetch('/static/data/ne_110m_admin_0_countries.geojson').then(r => r.json()).then(data => L.geoJSON(data, {interactive:false,style:{color:'#82aeca',weight:.6,fillColor:palette.land,fillOpacity:.94}}).addTo(map));
  const latlngs = points.map((point, index) => { const marker=L.circleMarker([point.lat,point.lng],{radius:7,color:'#fff',weight:2,fillColor:index?palette.blue:palette.yellow,fillOpacity:1}).addTo(map); marker.bindTooltip(`${point.label}: ${point.place}${point.date?` · ${point.date}`:''}`); return [point.lat,point.lng]; });
  if(latlngs.length>1)L.polyline(latlngs,{color:palette.navy,weight:2,dashArray:'5 7'}).addTo(map);
  if(latlngs.length===1)map.setView(latlngs[0],7);else map.fitBounds(latlngs,{padding:[35,35],maxZoom:7});
})();
