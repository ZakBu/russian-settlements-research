import type { Map as LibreMap } from 'maplibre-gl';

export type ResearchLayer = {
  id: string; researchId: string; title: string; description: string;
  geometry: 'point' | 'line' | 'polygon'; path: string; palette: string;
  unit: string; period: string; evidence: string;
  valueLabels?: Record<string, string>;
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
export function researchCategoryPalette(dark = false): string[] {
  return dark ? ['#7294FF','#5BD6AE','#FFAA76','#BCA1F3','#E8CA75'] : ['#244CFF','#16806A','#C65B24','#7955C5','#9C7715'];
}
export function researchValueLabel(meta: ResearchLayer, value: unknown): string | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined;
  return Object.entries(meta.valueLabels || {}).find(([key]) => Number(key) === value)?.[1];
}
export function researchLegendEntries(meta: ResearchLayer, data?: LayerPayload | null, dark = false) {
  if (!meta.valueLabels) return [];
  const present = data ? new Set(data.features.map(f => f.properties?.value).filter(v => typeof v === 'number' && Number.isFinite(v))) : null;
  const palette = researchCategoryPalette(dark);
  return Object.entries(meta.valueLabels).map(([key,label]) => ({value:Number(key),label}))
    .filter(row => !present || present.has(row.value)).sort((a,b) => a.value-b.value)
    .map(row => ({...row,color:palette[Math.abs(Math.round(row.value))%5]}));
}
export function renderResearchLayer(map: LibreMap, meta: ResearchLayer, data: LayerPayload, visible: boolean, dark: boolean) {
  const sourceId = `research-${meta.id}`;
  const stats = layerStats(data);
  const blue = dark ? '#7294FF' : '#244CFF', pale = dark ? '#263A71' : '#C9D4FF', unknown = dark ? '#8995AF' : '#8993A8';
  let fill: any = blue;
  if (stats.min !== null && stats.max !== null && stats.min !== stats.max) {
    fill = ['interpolate', ['linear'], ['get', 'value'], stats.min, pale, stats.max, blue];
    if (meta.palette === 'population-change' && stats.min < 0 && stats.max > 0) fill = ['interpolate', ['linear'], ['get', 'value'], stats.min, dark ? '#FFAA76' : '#C65B24', 0, dark ? '#B0BEDF' : '#CED7EC', stats.max, blue];
  }
  // A single visible category still uses its named class color. It must not
  // become blue merely because min equals max (for example one violet band).
  if (stats.known && (meta.palette === 'categorical' || meta.palette === 'service-type')) {
    const category = researchCategoryPalette(dark);
    fill = ['match', ['%', ['abs', ['round', ['get', 'value']]], 5], 0, category[0], 1, category[1], 2, category[2], 3, category[3], category[4]];
  }
  fill = ['case', ['==', ['get', 'value'], null], unknown, fill];
  const namedCategories = !!meta.valueLabels && ['categorical','service-type'].includes(meta.palette);
  const polygonOpacity = namedCategories ? .6 : .3;
  const polygonOutline = namedCategories ? fill : blue;
  const polygonOutlineWidth = namedCategories ? 1 : 1.5;
  if (!map.getSource(sourceId)) map.addSource(sourceId, { type: 'geojson', data: data as any });
  const ids = layerIds(meta);
  if (!map.getLayer(ids[0])) {
    if (meta.geometry === 'point') map.addLayer({ id: ids[0], type: 'circle', source: sourceId, paint: { 'circle-radius': 7, 'circle-color': fill, 'circle-stroke-color': dark ? '#F4F6FF' : '#FFFFFF', 'circle-stroke-width': 1.5, 'circle-opacity': .9 } });
    if (meta.geometry === 'line') map.addLayer({ id: ids[0], type: 'line', source: sourceId, paint: { 'line-width': 3, 'line-color': fill, 'line-opacity': .9 } });
    if (meta.geometry === 'polygon') {
      map.addLayer({ id: ids[0], type: 'fill', source: sourceId, paint: { 'fill-color': fill, 'fill-opacity': polygonOpacity } });
      map.addLayer({ id: ids[1], type: 'line', source: sourceId, paint: { 'line-color': polygonOutline, 'line-width': polygonOutlineWidth } });
    }
  }
  map.setPaintProperty(ids[0], meta.geometry === 'point' ? 'circle-color' : meta.geometry === 'line' ? 'line-color' : 'fill-color', fill);
  if (meta.geometry === 'polygon') {
    map.setPaintProperty(ids[0], 'fill-opacity', polygonOpacity);
    map.setPaintProperty(ids[1], 'line-color', polygonOutline);
    map.setPaintProperty(ids[1], 'line-width', polygonOutlineWidth);
  }
  if (meta.geometry === 'point') {
    const min = stats.min, max = stats.max;
    map.setPaintProperty(ids[0], 'circle-radius', min !== null && max !== null && min !== max ? ['interpolate', ['linear'], ['coalesce', ['get', 'value'], min], min, 5, max, 13] : 7);
  }
  ids.forEach(id => map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none'));
}
