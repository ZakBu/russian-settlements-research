import type { Map as LibreMap } from 'maplibre-gl';

export type ResearchLayer = {
  id: string; researchId: string; title: string; description: string;
  geometry: 'point' | 'line' | 'polygon'; path: string; palette: string;
  unit: string; period: string; evidence: string;
  source: { title: string; url: string; sha256?: string; sourceCommit?: string };
};
export type LayerPayload = { type: 'FeatureCollection'; features: any[] };
export function layerIds(meta: ResearchLayer) {
  return meta.geometry === 'polygon' ? [`research-${meta.id}-fill`, `research-${meta.id}-outline`] : [`research-${meta.id}`];
}
export function layerStats(data: LayerPayload) {
  const values = data.features.map(f => f.properties?.value).filter(v => typeof v === 'number' && Number.isFinite(v));
  return { count: data.features.length, known: values.length, min: values.length ? values.reduce((a,b) => Math.min(a,b), Infinity) : null, max: values.length ? values.reduce((a,b) => Math.max(a,b), -Infinity) : null };
}
export function renderResearchLayer(map: LibreMap, meta: ResearchLayer, data: LayerPayload, visible: boolean, dark: boolean) {
  const sourceId = `research-${meta.id}`;
  const stats = layerStats(data);
  const blue = dark ? '#7294FF' : '#244CFF', pale = dark ? '#263A71' : '#C9D4FF', unknown = dark ? '#8995AF' : '#8993A8';
  let fill: any = blue;
  if (stats.min !== null && stats.max !== null && stats.min !== stats.max) {
    fill = ['interpolate', ['linear'], ['get', 'value'], stats.min, pale, stats.max, blue];
    if (meta.palette === 'population-change' && stats.min < 0 && stats.max > 0) fill = ['interpolate', ['linear'], ['get', 'value'], stats.min, dark ? '#FFAA76' : '#C65B24', 0, dark ? '#B0BEDF' : '#CED7EC', stats.max, blue];
    if (meta.palette === 'categorical' || meta.palette === 'service-type') fill = ['match', ['%', ['abs', ['round', ['get', 'value']]], 5], 0, blue, 1, dark ? '#5BD6AE' : '#16806A', 2, dark ? '#FFAA76' : '#C65B24', 3, dark ? '#BCA1F3' : '#7955C5', dark ? '#E8CA75' : '#9C7715'];
  }
  fill = ['case', ['==', ['get', 'value'], null], unknown, fill];
  if (!map.getSource(sourceId)) map.addSource(sourceId, { type: 'geojson', data: data as any });
  const ids = layerIds(meta);
  if (!map.getLayer(ids[0])) {
    if (meta.geometry === 'point') map.addLayer({ id: ids[0], type: 'circle', source: sourceId, paint: { 'circle-radius': 7, 'circle-color': fill, 'circle-stroke-color': dark ? '#F4F6FF' : '#FFFFFF', 'circle-stroke-width': 1.5, 'circle-opacity': .9 } });
    if (meta.geometry === 'line') map.addLayer({ id: ids[0], type: 'line', source: sourceId, paint: { 'line-width': 3, 'line-color': fill, 'line-opacity': .9 } });
    if (meta.geometry === 'polygon') {
      map.addLayer({ id: ids[0], type: 'fill', source: sourceId, paint: { 'fill-color': fill, 'fill-opacity': .3 } });
      map.addLayer({ id: ids[1], type: 'line', source: sourceId, paint: { 'line-color': blue, 'line-width': 1.5 } });
    }
  }
  map.setPaintProperty(ids[0], meta.geometry === 'point' ? 'circle-color' : meta.geometry === 'line' ? 'line-color' : 'fill-color', fill);
  if (meta.geometry === 'point') {
    const min = stats.min, max = stats.max;
    map.setPaintProperty(ids[0], 'circle-radius', min !== null && max !== null && min !== max ? ['interpolate', ['linear'], ['coalesce', ['get', 'value'], min], min, 5, max, 13] : 7);
  }
  ids.forEach(id => map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none'));
}
