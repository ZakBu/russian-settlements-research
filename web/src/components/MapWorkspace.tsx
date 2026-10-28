import { useEffect, useRef, useState } from 'react';
import maplibregl, { type Map as LibreMap } from 'maplibre-gl';
import * as echarts from 'echarts';
import { layerIds, layerStats, renderResearchLayer, type ResearchLayer, type LayerPayload } from './custom-map-layers';
import 'maplibre-gl/dist/maplibre-gl.css';
import './map-workspace.css';
import siteAssets from '../../../data/site_assets.json';
import {addContextBasemap,type ContextBasemap} from './map-basemap';
import {settlementPopulationCutoff,settlementMagnitude,settlementVisibilityFilter} from '../lib/map-density';

type Properties = Record<string, any>;
type Feature = { type: 'Feature'; id?: string | number; geometry: { type: string; coordinates: any }; properties: Properties };
type Collection = { type: 'FeatureCollection'; features: Feature[] };
type Mode = 'settlement' | 'district' | 'region';
type Period = '2002-2010' | '2010-2021' | '2002-2021' | '2002' | '2010' | '2021';
type Layers = { population: boolean; schools: boolean; medical: boolean; links: boolean; centres: boolean; districts: boolean; regions: boolean };
type Selection = { mode: Mode; feature: Feature };
type Manifest = { generatedAt?: string; sourceCommit?: string; counts?: Record<string, number>; sources?: any; [key: string]: any };
const boundaryStamp=(key:'regions'|'districts')=>{const asset=siteAssets.boundaries.find(a=>a.id===key)!;return `${asset.provider} · ${asset.snapshotDate.split('-').reverse().join('.')}`};
const selectionLabel=(s:Selection)=>s.mode==='district'&&s.feature.properties.kind==='undivided'?'Справочная территория':names[s.mode];
const empty: Collection = { type: 'FeatureCollection', features: [] };
const defaultLayers: Layers = { population: true, schools: false, medical: false, links: false, centres: false, districts: false, regions: true };
const format = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });
const number = (v: any) => v === null || v === undefined || v === '' || !Number.isFinite(Number(v)) ? null : Number(v);
const shown = (v: any) => number(v) === null ? 'Нет сведений' : format.format(Number(v));
const titleOf = (f: Feature) => f.properties.nameRu || f.properties.name || f.properties.title || f.properties.shapeName || f.properties.id;
const idOf = (f: Feature) => String(f.properties.id ?? f.id ?? '');
function searchKey(value: any) {
  // Transliteration improves discovery only; display names use the Russian source field.
  const letters: Record<string, string> = { а:'a',б:'b',в:'v',г:'g',д:'d',е:'e',ё:'e',ж:'zh',з:'z',и:'i',й:'y',к:'k',л:'l',м:'m',н:'n',о:'o',п:'p',р:'r',с:'s',т:'t',у:'u',ф:'f',х:'kh',ц:'ts',ч:'ch',ш:'sh',щ:'shch',ъ:'',ы:'y',ь:'',э:'e',ю:'yu',я:'ya' };
  return String(value || '').toLowerCase().replace(/ий\b/g, 'y').split('').map(letter => letters[letter] ?? letter).join('').replace(/(oblast|district|republic|rayon|raion|respublika|oblasty)/g, ' ').replace(/(skaya|skiy|sky)\b/g, 'sk').replace(/[^a-z0-9]+/g, ' ').trim();
}
const names: Record<Mode, string> = { settlement: 'Населённый пункт', district: 'Район / округ', region: 'Регион' };
const color = (dark: boolean) => ({ blue: dark ? '#7294FF' : '#244CFF', ink: dark ? '#F4F6FF' : '#10265C', orange: dark ? '#FFAA76' : '#C65B24', green: dark ? '#5BD6AE' : '#16806A', gray: dark ? '#8995AF' : '#8993A8', line: dark ? '#354266' : '#D2D9ED' });

function populationCollection(payload: any): Collection {
  if (payload?.format !== 'settlements-columnar-v1' || !Array.isArray(payload.rows) || !Array.isArray(payload.regions)) throw new Error('Некорректный формат населения');
  return { type: 'FeatureCollection', features: payload.rows.map((row: any[]) => {
    if (!Array.isArray(row) || row.length !== 10 || typeof row[0] !== 'string' || typeof payload.regions[row[2]] !== 'string') throw new Error('Некорректная строка населения');
    return { type: 'Feature', geometry: { type: 'Point', coordinates: [row[3], row[4]] },
      properties: { id: row[0], shard: row[0].slice(0, 2), name: row[1], region: payload.regions[row[2]], p02: row[5], p10: row[6], p21: row[7], change: row[8], comparable: row[9] } };
  }) };
}

function readLocation() {
  const q = new URLSearchParams(window.location.search);
  const requested = q.get('layers');
  const enabled = requested?.split(',') || [];
  const layers = requested === null ? defaultLayers : Object.fromEntries(Object.keys(defaultLayers).map(k => [k, enabled.includes(k) || (['schools', 'medical'].includes(k) && enabled.includes('services'))])) as Layers;
  const p = q.get('period');
  return { layers, period: (['2002-2010', '2010-2021', '2002-2021', '2002', '2010', '2021'].includes(p || '') ? p : '2002-2021') as Period, mode: (['settlement', 'district', 'region'].includes(q.get('mode') || '') ? q.get('mode') : 'settlement') as Mode, selected: q.get('selection') || q.get('selected') || '', lat: number(q.get('lat')), lng: number(q.get('lng')), zoom: number(q.get('zoom')) };
}

function inRing(point: number[], ring: number[][]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i], b = ring[j];
    if ((a[1] > point[1]) !== (b[1] > point[1]) && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
}
function contains(f: Feature, point: number[]) {
  const polygons = f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates : [f.geometry.coordinates];
  return polygons.some((rings: number[][][]) => rings.length && inRing(point, rings[0]) && !rings.slice(1).some(r => inRing(point, r)));
}
function bounds(f: Feature): [[number, number], [number, number]] | null {
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
  const walk = (a: any) => {
    if (typeof a?.[0] === 'number') { west = Math.min(west, a[0]); south = Math.min(south, a[1]); east = Math.max(east, a[0]); north = Math.max(north, a[1]); }
    else if (Array.isArray(a)) a.forEach(walk);
  };
  walk(f.geometry.coordinates);
  return Number.isFinite(west) ? [[west, south], [east, north]] : null;
}
function Charts({ features, selected, dark }: { features: Feature[]; selected: Selection; dark: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!host.current) return;
    const chart = echarts.init(host.current, undefined, { renderer: 'svg' });
    const c = color(dark);
    const eligible = selected.mode === 'settlement' ? features : features.filter(f => f.properties.comparable === true && [f.properties.p02, f.properties.p10, f.properties.p21].every(v => number(v) !== null));
    const sums = ['p02', 'p10', 'p21'].map(key => {
      if (selected.mode !== 'settlement') return number(selected.feature.properties[key]);
      const values = eligible.map(f => number(f.properties[key])).filter(v => v !== null) as number[];
      return values.length ? values.reduce((a, b) => a + b, 0) : null;
    });
    const known2021=selected.mode==='settlement'?features.filter(f=>number(f.properties.p21)!==null).length:Number(selected.feature.properties.p21KnownCount||0);
    const bins = [0, 0, 0, 0, 0];
    features.forEach(f => { const p = number(f.properties.p21); if (p !== null) bins[p < 100 ? 0 : p < 1000 ? 1 : p < 10000 ? 2 : p < 100000 ? 3 : 4]++; });
    if (selected.mode !== 'settlement' && Array.isArray(selected.feature.properties.sizeBins)) selected.feature.properties.sizeBins.forEach((v: number, i: number) => { if (i < 5) bins[i] = v; });
    chart.setOption({
      backgroundColor: 'transparent', textStyle: { fontFamily: 'Golos Text, sans-serif', color: c.ink }, animationDuration: 250,
      tooltip: { trigger: 'axis', confine: true, backgroundColor: dark ? '#14213D' : '#FFFFFF', textStyle: { color: c.ink }, borderColor: c.line, valueFormatter: (v: any) => shown(v) },
      title: [{ text: sums.every(value=>value===null)?'Население, человек\nНет зачтённых данных':'Население, человек', left: '3%', top: 3, textStyle: { color: c.ink, fontSize: 13, fontWeight: 500 } }, { text: known2021?'НП по населению 2021 года':'Людность, 2021\nНет зачтённых данных', left: '55%', top: 3, textStyle: { color: c.ink, fontSize: 13, fontWeight: 500 } }],
      grid: [{ left: '4%', right: '54%', top: 43, bottom: 28, containLabel: true }, { left: '55%', right: '4%', top: 43, bottom: 28, containLabel: true }],
      xAxis: [{ type: 'category', data: ['2002', '2010', '2021'], axisLine: { lineStyle: { color: c.line } }, axisTick: { show: false }, axisLabel: { color: c.ink } }, { type: 'value', gridIndex: 1, minInterval: 1, axisLabel: { color: c.ink }, splitLine: { lineStyle: { color: c.line } } }],
      yAxis: [{ type: 'value', axisLabel: { color: c.ink, formatter: (v: number) => format.format(v) }, splitLine: { lineStyle: { color: c.line, type: 'dotted' } } }, { type: 'category', gridIndex: 1, data: ['До 100', '100–999', '1–10 тыс.', '10–100 тыс.', 'От 100 тыс.'], axisLabel: { color: c.ink }, axisTick: { show: false }, axisLine: { show: false } }],
      series: [{ name: 'Население', type: 'bar', data: sums, barMaxWidth: 35, itemStyle: { color: c.blue }, decal: { symbol: 'rect', dashArrayX: [1, 2], dashArrayY: [1, 2], color: 'rgba(255,255,255,.25)' } }, { name: 'Число НП', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: known2021?bins:bins.map(()=>null), barMaxWidth: 15, itemStyle: { color: c.blue }, label: { show: true, position: 'right', color: c.ink } }],
    });
    const observer = new ResizeObserver(() => chart.resize()); observer.observe(host.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [features, selected, dark]);
  return <div ref={host} className="map-charts" role="img" aria-label="Динамика населения по трём переписям и распределение населённых пунктов по людности" />;
}

export default function MapWorkspace({ base = '/', research }: { base?: string; research?: string }) {
  const root = base.endsWith('/') ? base : `${base}/`;
  const mapElement = useRef<HTMLDivElement>(null);
  const map = useRef<LibreMap | null>(null);
  const loaded = useRef(false);
  const pendingCollections = useRef<Record<string, Promise<void> | undefined>>({});
  const loadedCollections = useRef(new Set<string>());
  const failedCollections = useRef(new Set<string>());
  const sourceCollections = useRef<Record<string, Collection>>({});
  const deferredSelection = useRef<ReturnType<typeof readLocation> | null>(null);
  const customCache = useRef<Record<string, LayerPayload>>({});
  const customPending = useRef(new Set<string>());
  const customFailure = useRef(new Set<string>());
  const customRegistryRef = useRef<ResearchLayer[]>([]);
  const initialLocation = useRef<ReturnType<typeof readLocation> | null>(null);
  const labels = useRef<maplibregl.Marker[]>([]);
  const basemap = useRef<ContextBasemap|null>(null);
  const contextAvailable=useRef(false);
  const renderLabels = useRef<() => void>(() => {});
  const activeMode = useRef<Mode>('settlement');
  const dataRef = useRef<Record<string, Collection>>({ settlements: empty, districts: empty, regions: empty, services: empty, links: empty, centres: empty });
  const [collections, setCollections] = useState<Record<string, Collection>>(dataRef.current);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [registry, setRegistry] = useState<ResearchLayer[]>([]);
  const [registryError, setRegistryError] = useState(false);
  const [customActive, setCustomActive] = useState<string[]>([]);
  const [customRevision, setCustomRevision] = useState(0);
  const [customErrors, setCustomErrors] = useState<Record<string, string>>({});
  const customActiveRef = useRef<string[]>([]);
  customActiveRef.current = customActive;
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(true);
  const [pendingKeys, setPendingKeys] = useState<string[]>([]);
  const [mapError, setMapError] = useState('');
  const [basemapUnavailable, setBasemapUnavailable] = useState(false);
  const [layers, setLayers] = useState<Layers>(defaultLayers);
  const [mode, setMode] = useState<Mode>('settlement');
  const [period, setPeriod] = useState<Period>('2002-2021');
  const [opacity, setOpacity] = useState(80);
  const [panel, setPanel] = useState(true);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [members, setMembers] = useState<Feature[]>([]);
  const [aggregateBusy, setAggregateBusy] = useState(false);
  const [details, setDetails] = useState<any>(null);
  const [detailError, setDetailError] = useState(false);
  const polygonCache=useRef<Record<string,Promise<Record<string,Feature>>>>({});
  const polygonFit=useRef(false);
  const [placeBoundary,setPlaceBoundary]=useState<{id:string;feature:Feature}|null>(null);
  const [boundaryStatus,setBoundaryStatus]=useState<'loading'|'available'|'missing'|'error'>('loading');
  const [query, setQuery] = useState('');
  const [searchFocus, setSearchFocus] = useState(false);
  const [copied, setCopied] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(false);
  const selectRef = useRef<(s: Selection, fit?: boolean, history?: boolean) => void>(() => {});
  const syncRef = useRef<() => void>(() => {});

  const updateUrl = (s: Selection | null = selection, push = false) => {
    if (!map.current) return;
    const u = new URL(window.location.href);
    u.searchParams.set('layers', [...Object.entries(layers).filter(([, yes]) => yes).map(([key]) => key), ...customActive].join(','));
    u.searchParams.set('period', period); u.searchParams.set('mode', mode);
    if (s) { u.searchParams.set('selection', idOf(s.feature)); u.searchParams.set('mode', s.mode); }
    else u.searchParams.delete('selection');
    const center = map.current.getCenter();
    u.searchParams.set('lat', center.lat.toFixed(4)); u.searchParams.set('lng', center.lng.toFixed(4)); u.searchParams.set('zoom', map.current.getZoom().toFixed(2));
    if (research) u.searchParams.set('research', research);
    if (push && u.href !== window.location.href) window.history.pushState({}, '', u); else window.history.replaceState({}, '', u);
  };
  syncRef.current = () => updateUrl();

  function zoomTo(feature: Feature,detail=false) {
    const box = bounds(feature); if (!box || !map.current) return;
    const mobile = window.innerWidth < 760;
    map.current.fitBounds(box, { padding: { top: 75, left: !mobile && panel ? 325 : 35, right: 45, bottom: mobile ? 240 : 280 }, maxZoom: feature.geometry.type === 'Point' ? (detail?15.5:settlementMagnitude(feature.properties)<20000?14:11) : feature.properties.settlementBoundary?14:9, duration: 650 });
  }
  const cancelPendingSelection=()=>{deferredSelection.current=null;if(initialLocation.current)initialLocation.current.selected=''};
  const select = (s: Selection, fit = false, history = true) => {
    cancelPendingSelection();
    polygonFit.current=history;setPlaceBoundary(null);setBoundaryStatus('loading');
    setSelection(s); setMode(s.mode); setCollapsed(false); setDetails(null); setDetailError(false);
    if (window.innerWidth < 760) setPanel(false);
    if (fit) zoomTo(s.feature);
    updateUrl(s, history);
  };
  selectRef.current = select;

  useEffect(() => {
    const state = readLocation(); initialLocation.current = state; setLayers(state.layers); setPeriod(state.period); setMode(state.mode); activeMode.current = state.mode;
    const custom = (new URLSearchParams(window.location.search).get('layers') || '').split(',').filter(id => /^[a-z0-9][a-z0-9-]*$/.test(id) && !(id in defaultLayers) && id !== 'services');
    setCustomActive([...new Set(custom)]);
    const readTheme = () => setDark(document.documentElement.dataset.theme === 'dark' || document.documentElement.classList.contains('dark'));
    readTheme(); const obs = new MutationObserver(readTheme); obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class'] });
    return () => obs.disconnect();
  }, []);

  const loadCollection = (key: string): Promise<void> => {
    if (loadedCollections.current.has(key) || failedCollections.current.has(key)) return Promise.resolve();
    if (pendingCollections.current[key]) return pendingCollections.current[key]!;
    const paths: Record<string, string> = { settlements: 'settlements.compact.json', 'settlements-overview':'settlements.overview.json', regions: 'regions-display.geojson', districts: 'districts-display.geojson' };
    setPendingKeys(previous => [...previous, key]);
    pendingCollections.current[key] = (async () => {
      try {
        const source = siteAssets.boundaries.find(asset => asset.id === key);
        const version = source ? `?v=${source.sha256.slice(0, 12)}` : '';
        const response = await fetch(`${root}data/${paths[key] || `${key}.geojson`}${version}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        const populationKey=key==='settlements'||key==='settlements-overview';
        const target=populationKey?'settlements':key;
        const body = populationKey ? populationCollection(payload) : payload as Collection;
        if (body.type !== 'FeatureCollection' || !Array.isArray(body.features)) throw new Error('Неожиданный формат');
        loadedCollections.current.add(key);
        // Publish each usable source immediately; optional geography never blocks population.
        if(key!=='settlements-overview'||!loadedCollections.current.has('settlements')){dataRef.current = { ...dataRef.current, [target]: body }; setCollections(dataRef.current);}
        setErrors(previous => { const next = { ...previous }; delete next[key];if(key==='settlements')delete next['settlements-overview']; return next; });
        const requested = deferredSelection.current || initialLocation.current;
        if (requested?.selected && key === (requested.mode === 'settlement' ? 'settlements' : `${requested.mode}s`)) {
          const feature = body.features.find(f => idOf(f) === requested.selected);
          if (feature) { selectRef.current({ mode: requested.mode, feature }, false, false); deferredSelection.current = null; }
        }
      } catch (error) {
        failedCollections.current.add(key);if(key==='settlements-overview'){void loadCollection('settlements')}else setErrors(previous => ({ ...previous, [key]: String(error) }));
      } finally {
        delete pendingCollections.current[key]; setPendingKeys(previous => previous.filter(item => item !== key)); if(key==='settlements'||key==='settlements-overview'&&!failedCollections.current.has(key))setBusy(false);
      }
    })();
    return pendingCollections.current[key]!;
  };
  const loadData = async () => {
    failedCollections.current.clear(); setErrors({});
    if (!dataRef.current.settlements.features.length) setBusy(true);
    const requested = readLocation();
    void loadCollection((requested.zoom??2.6)>=7||requested.selected&&requested.mode==='settlement'||query.trim().length>=2||searchFocus?'settlements':'settlements-overview');void loadCollection('regions');
    // Small source-backed overlays are independent; district polygons stay on demand.
    for (const key of ['services', 'links', 'centres']) void loadCollection(key);
    if (requested.mode === 'district' || requested.layers.districts || query.trim().length >= 2) void loadCollection('districts');
    try { const r = await fetch(`${root}data/manifest.json`); if (r.ok) setManifest(await r.json()); } catch { /* Missing provenance does not hide available geography. */ }
  };
  useEffect(() => { void loadData(); }, [root]);
  useEffect(()=>{if(searchFocus||query.trim().length>=2)void loadCollection('settlements')},[searchFocus,query]);
  useEffect(() => {
    if (layers.districts || mode === 'district' || query.trim().length >= 2) void loadCollection('districts');
  }, [layers.districts, mode, query]);
  const loadRegistry = async () => {
    try {
      const response = await fetch(`${root}data/layers.json`); if (!response.ok) throw new Error('registry');
      const rows = await response.json();
      if (!Array.isArray(rows)) throw new Error('registry-format');
      const accepted = rows.filter((row: ResearchLayer) => /^[a-z0-9][a-z0-9-]*$/.test(row.id) && ['point', 'line', 'polygon'].includes(row.geometry) && row.path === `custom-layers/${row.id}.geojson`);
      customRegistryRef.current = accepted; setRegistry(accepted); setRegistryError(false);
    } catch { setRegistryError(true); }
  };
  useEffect(() => { void loadRegistry(); }, [root]);

  useEffect(() => {
    const instance = map.current; if (!instance) return;
    const apply = () => {
      if (!loaded.current) return;
      for (const meta of registry) {
        const enabled = customActive.includes(meta.id), data = customCache.current[meta.id];
        if (data) { renderResearchLayer(instance, meta, data, enabled, dark); continue; }
        if (!enabled || customPending.current.has(meta.id) || customFailure.current.has(meta.id)) continue;
        customPending.current.add(meta.id); setCustomRevision(v => v + 1);
        fetch(`${root}data/${meta.path}`).then(response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); }).then((payload: LayerPayload) => {
          if (payload.type !== 'FeatureCollection' || !Array.isArray(payload.features)) throw new Error('Некорректный пространственный слой');
          customCache.current[meta.id] = payload;
          setCustomErrors(previous => { const next = { ...previous }; delete next[meta.id]; return next; });
        }).catch(error => { customFailure.current.add(meta.id); setCustomErrors(previous => ({ ...previous, [meta.id]: String(error.message || error) })); }).finally(() => { customPending.current.delete(meta.id); setCustomRevision(v => v + 1); });
      }
    };
    if (loaded.current) apply(); else instance.once('load', apply);
    if (loaded.current && !busy) updateUrl();
    return () => { instance.off('load', apply); };
  }, [registry, customActive, dark, customRevision, collections, busy]);

  useEffect(() => {
    if (!mapElement.current) return;
    const initial = readLocation();
    let instance: LibreMap;
    try {
      instance = new maplibregl.Map({ container: mapElement.current, style: { version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#F4F6FF' } }] }, center: [initial.lng ?? 88, initial.lat ?? 59], zoom: initial.zoom ?? 2.6, minZoom: 1.6, maxZoom: 19, maxTileCacheSize:96, locale:{'NavigationControl.ZoomIn':'Приблизить','NavigationControl.ZoomOut':'Отдалить','NavigationControl.ResetBearing':'Север сверху','AttributionControl.ToggleAttribution':'Источники карты','ScaleControl.Meters':'м','ScaleControl.Kilometers':'км','Popup.Close':'Закрыть','Marker.Title':'Метка','Map.Title':'Интерактивная карта расселения'}, attributionControl: false });
    } catch { setMapError('Браузер не смог открыть WebGL-карту. Попробуйте обновить страницу или включить аппаратное ускорение.'); return; }
    map.current = instance;
    let previousCutoff=-1;
    renderLabels.current = () => {
      labels.current.forEach(label => label.remove()); labels.current = [];
      if (!loaded.current) return;
      const zoom=instance.getZoom(),visible=instance.getBounds(),cutoff=settlementPopulationCutoff(zoom);
      if(previousCutoff!==cutoff){instance.setFilter('settlements-point',settlementVisibilityFilter(zoom) as any);previousCutoff=cutoff}
      if(contextAvailable.current && zoom>=4)return;
      const candidates=dataRef.current.settlements.features.filter(feature=>visible.contains(feature.geometry.coordinates)&&settlementMagnitude(feature.properties)>=cutoff).sort((a,b)=>settlementMagnitude(b.properties)-settlementMagnitude(a.properties));
      const occupied:{left:number;right:number;top:number;bottom:number}[]=[];
      const canvas=instance.getCanvas();
      for(const feature of candidates){
        const point=feature.geometry.coordinates,position=instance.project(point),text=String(titleOf(feature));
        const width=Math.min(190,Math.max(50,text.length*6.5)),right=position.x+width+12>canvas.clientWidth;
        const box={left:right?position.x-width-10:position.x+8,right:right?position.x-8:position.x+width+10,top:position.y-20,bottom:position.y+2};
        if(box.left<0||box.right>canvas.clientWidth||box.top<0||box.bottom>canvas.clientHeight||occupied.some(p=>box.left<p.right+8&&box.right>p.left-8&&box.top<p.bottom+6&&box.bottom>p.top-6))continue;
        const element=document.createElement('span');element.className='map-place-label';element.textContent=text;
        labels.current.push(new maplibregl.Marker({element,anchor:right?'right':'left',offset:[right?-7:7,-8]}).setLngLat(point).addTo(instance));occupied.push(box);
        if(labels.current.length>=(zoom<5?20:zoom<8?36:60))break;
      }
    };
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    instance.addControl(new maplibregl.ScaleControl({ unit: 'metric', maxWidth: 150 }), 'bottom-left');
    instance.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: `Переписи 2002/2010/2021 · ${boundaryStamp('regions')}` }), 'bottom-right');
    instance.on('load', () => {
      void addContextBasemap(instance,{dark:document.documentElement.dataset.theme==='dark',onStatus:available=>{contextAvailable.current=available;setBasemapUnavailable(!available);renderLabels.current()}}).then(handle=>{if(map.current===instance){basemap.current=handle;handle.setTheme(document.documentElement.dataset.theme==='dark')}else handle.dispose()});
      const boundary = (key: string, fill: string) => {
        instance.addSource(key, { type: 'geojson', data: empty as any });
        instance.addLayer({ id: `${key}-fill`, type: 'fill', source: key, paint: { 'fill-color': fill, 'fill-opacity': key === 'regions' ? .012 : .008 } });
        instance.addLayer({ id: `${key}-line`, type: 'line', source: key, paint: { 'line-color': fill, 'line-width': key === 'regions' ? 1 : .65, 'line-opacity': .65, 'line-dasharray': key === 'districts' ? [3, 3] : [1, 0] } });
      };
      boundary('regions', '#244CFF'); boundary('districts', '#7955C5');
      instance.addSource('settlements', { type: 'geojson', data: empty as any, cluster: false, attribution: 'Связанная база переписей 2002/2010/2021' });
      instance.addLayer({ id: 'settlements-point', type: 'circle', source: 'settlements', filter: settlementVisibilityFilter(instance.getZoom()) as any, paint: { 'circle-color': '#244CFF', 'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 2, 8, 2.7, 14, 3.6], 'circle-stroke-color': '#F4F6FF', 'circle-stroke-width': .5, 'circle-opacity': .8 } });
      instance.addSource('links', { type: 'geojson', data: empty as any });
      instance.addLayer({ id: 'links-line', type: 'line', source: 'links', paint: { 'line-color': '#244CFF', 'line-width': 1.6, 'line-opacity': .75, 'line-dasharray': [4, 2] } });
      instance.addSource('services', { type: 'geojson', data: empty as any });
      instance.addLayer({ id: 'services-point', type: 'circle', source: 'services', paint: { 'circle-color': ['match', ['get', 'family'], 'schools', '#16806A', 'medical', '#C65B24', '#7955C5'], 'circle-radius': 5, 'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': 1.3 } });
      instance.addSource('centres', { type: 'geojson', data: empty as any });
      instance.addLayer({ id: 'centres-point', type: 'circle', source: 'centres', paint: { 'circle-color': '#F4F6FF', 'circle-radius': 7, 'circle-stroke-color': '#7955C5', 'circle-stroke-width': 2.5, 'circle-opacity': .8 } });
      instance.addSource('selected', { type: 'geojson', data: empty as any });
      instance.addLayer({ id: 'selected-fill', type: 'fill', source: 'selected', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': '#244CFF', 'fill-opacity': ['case',['==',['get','settlementBoundary'],true],.13,.08] } });
      instance.addLayer({ id: 'selected-line', type: 'line', source: 'selected', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'line-color': '#244CFF', 'line-width': ['case',['==',['get','settlementBoundary'],true],2.5,2] } });
      instance.addLayer({ id: 'selected-point', type: 'circle', source: 'selected', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-color': '#244CFF', 'circle-radius': 7, 'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': 3 } });
      loaded.current = true; refreshMap(instance, dataRef.current); renderLabels.current();
    });
    instance.on('click', async event => {
      if (!loaded.current) return;
      const activeResearch = customRegistryRef.current.filter(meta => customActiveRef.current.includes(meta.id));
      const researchIds = activeResearch.flatMap(layerIds).filter(id => instance.getLayer(id));
      const hit = researchIds.length ? instance.queryRenderedFeatures(event.point, { layers: researchIds })[0] : null;
      if (hit) {
        const meta = activeResearch.find(row => layerIds(row).includes(hit.layer.id));
        if (meta) {
          const node = document.createElement('div'); node.className = 'map-evidence-popup';
          const heading = document.createElement('strong'); heading.textContent = hit.properties.name || meta.title; node.append(heading);
          const value = document.createElement('p'); value.textContent = `${meta.title}: ${shown(hit.properties.value)}${number(hit.properties.value) === null ? '' : ` ${meta.unit}`}`; node.append(value);
          const evidence: Record<string, string> = { model: 'Модельная оценка', observation: 'Наблюдение', calculation: 'Расчёт', hypothesis: 'Гипотеза', method: 'Метод' };
          const context = document.createElement('small'); context.textContent = `${meta.period} · ${evidence[meta.evidence] || meta.evidence}`; node.append(context);
          const source = document.createElement('a'); source.textContent = `${meta.source?.title || 'Первичный источник'} ↗`;
          if (/^https?:\/\//.test(meta.source?.url || '')) { source.href = meta.source.url; source.target = '_blank'; source.rel = 'noopener noreferrer'; }
          node.append(source);
          const census = hit.properties.settlementId ? dataRef.current.settlements.features.find(f => idOf(f) === String(hit.properties.settlementId)) : null;
          if (census) selectRef.current({ mode: 'settlement', feature: census });
          new maplibregl.Popup({ closeButton: true, maxWidth: '330px' }).setLngLat(event.lngLat).setDOMContent(node).addTo(instance);
          return;
        }
      }
      const centre = instance.queryRenderedFeatures(event.point, { layers: ['centres-point'] })[0];
      if (centre) {
        const feature = dataRef.current.settlements.features.find(f => idOf(f) === String(centre.properties.id));
        if (feature) selectRef.current({ mode: 'settlement', feature });
        return;
      }
      const service = instance.queryRenderedFeatures(event.point, { layers: ['services-point', 'links-line'] })[0];
      if (service) {
        const node = document.createElement('div'); node.className = 'map-evidence-popup';
        const heading = document.createElement('strong'); heading.textContent = service.properties.name || service.properties.family || 'Обслуживание'; node.append(heading);
        const evidence: Record<string, string> = { normative_attachment: 'Документированное прикрепление', provider_reported_service: 'Сведения поставщика услуги' };
        const source = document.createElement('p'); source.textContent = `${evidence[service.properties.evidence] || service.properties.evidence || 'Сведения источника'} · ${service.properties.year || 'Год указан в источнике'}`; node.append(source);
        const provenance = document.createElement('a'); provenance.textContent = 'Открыть первичный источник ↗';
        if (/^https?:\/\//.test(service.properties.source || '')) { provenance.href = service.properties.source; provenance.target = '_blank'; provenance.rel = 'noopener noreferrer'; }
        node.append(provenance);
        const caution = document.createElement('small'); caution.textContent = 'Точка обозначает НП обслуживания, не координаты здания. Линия — связь, не дорожный маршрут и не измеренный поток.'; node.append(caution);
        new maplibregl.Popup({ closeButton: true, maxWidth: '290px' }).setLngLat(event.lngLat).setDOMContent(node).addTo(instance);
      }
      const currentMode = activeMode.current;
      if (currentMode === 'settlement') {
        const items = instance.queryRenderedFeatures([[event.point.x - 7, event.point.y - 7], [event.point.x + 7, event.point.y + 7]], { layers: ['settlements-point'] });
        if (items[0]) {
          const id = String(items[0].properties.id);
          const feature = dataRef.current.settlements.features.find(f => idOf(f) === id);
          if (feature) selectRef.current({ mode: 'settlement', feature });
        }
      } else {
        const feature = dataRef.current[`${currentMode}s`].features.find(f => contains(f, [event.lngLat.lng, event.lngLat.lat]));
        if (feature) selectRef.current({ mode: currentMode, feature });
      }
    });
    const cancelPolygonFit=()=>{polygonFit.current=false};
    instance.on('wheel',cancelPolygonFit);instance.on('dragstart',cancelPolygonFit);instance.on('touchstart',cancelPolygonFit);
    instance.on('move', event => { if(event.originalEvent)cancelPolygonFit(); });
    instance.on('moveend', () => { syncRef.current();if(instance.getZoom()>=7)void loadCollection('settlements');renderLabels.current(); });
    instance.on('error', event => { if (event.error?.message?.includes('WebGL')) setMapError('Ошибка отображения карты. Обновите страницу.'); });
    const resize = new ResizeObserver(() => instance.resize()); resize.observe(mapElement.current);
    const pop = () => {
      const s = readLocation(); setLayers(s.layers); setPeriod(s.period); setMode(s.mode);
      const custom = (new URLSearchParams(window.location.search).get('layers') || '').split(',').filter(id => /^[a-z0-9][a-z0-9-]*$/.test(id) && !(id in defaultLayers) && id !== 'services');
      setCustomActive([...new Set(custom)]);
      if (s.lat !== null && s.lng !== null) instance.jumpTo({ center: [s.lng, s.lat], zoom: s.zoom ?? instance.getZoom() });
      const key = s.mode === 'settlement' ? 'settlements' : `${s.mode}s`;
      const f = dataRef.current[key].features.find(item => idOf(item) === s.selected);
      if (f) selectRef.current({ mode: s.mode, feature: f }, false, false); else {
        setSelection(null); deferredSelection.current = s; if (s.selected) void loadCollection(key);
      }
    };
    window.addEventListener('popstate', pop);
    return () => { window.removeEventListener('popstate', pop); resize.disconnect(); labels.current.forEach(label => label.remove()); labels.current = []; loaded.current = false;contextAvailable.current=false; sourceCollections.current = {}; basemap.current?.dispose();basemap.current=null; instance.remove(); map.current = null; };
  }, []);

  function refreshMap(instance: LibreMap, data: Record<string, Collection>) {
    if (!loaded.current) return;
    Object.entries(data).forEach(([key, collection]) => {
      const source = instance.getSource(key) as maplibregl.GeoJSONSource | undefined;
      if (source && sourceCollections.current[key] !== collection) { source.setData(collection as any); sourceCollections.current[key] = collection; }
    });
  }
  useEffect(() => { if (map.current) { refreshMap(map.current, collections); renderLabels.current(); } }, [collections]);
  useEffect(() => {
    activeMode.current = mode;
    if (mode === 'district') setLayers(previous => ({ ...previous, districts: true }));
    if (mode === 'region') setLayers(previous => ({ ...previous, regions: true }));
  }, [mode]);
  useEffect(() => {
    const instance = map.current; if (!instance) return;
    const apply = () => {
      if (!loaded.current) return;
      const c = color(dark);
      instance.setPaintProperty('background', 'background-color', dark ? '#080F24' : '#F4F6FF');
      basemap.current?.setTheme(dark);
      [['population', ['settlements-point']], ['centres', ['centres-point']], ['links', ['links-line']], ['districts', ['districts-fill', 'districts-line']], ['regions', ['regions-fill', 'regions-line']]].forEach(([key, ids]) => (ids as string[]).forEach(id => instance.setLayoutProperty(id, 'visibility', layers[key as keyof Layers] ? 'visible' : 'none')));
      instance.setLayoutProperty('services-point', 'visibility', layers.schools || layers.medical ? 'visible' : 'none');
      instance.setFilter('services-point', ['in', ['get', 'family'], ['literal', [...(layers.schools ? ['schools'] : []), ...(layers.medical ? ['medical'] : [])]]]);
      const years = period.split('-');
      const [from, to] = [years[0], years[1] || years[0]].map(year => `p${year.slice(2)}`);
      const change: any = ['case', ['all', ['!=', ['get', 'comparable'], false], ['>', ['coalesce', ['get', from], 0], 0], ['!=', ['get', to], null]], ['*', 100, ['/', ['-', ['get', to], ['get', from]], ['get', from]]], -9999];
      const expression: any = ['case', ['==', change, -9999], c.gray, ['<', change, -10], c.orange, ['>', change, 10], c.blue, dark ? '#B0BEDF' : '#A5B5D8'];
      instance.setPaintProperty('settlements-point', 'circle-color', years.length === 1 ? ['case', ['==', ['get', from], null], c.gray, c.blue] : expression);
      instance.setPaintProperty('settlements-point', 'circle-radius', years.length === 1 ? ['interpolate', ['linear'], ['sqrt', ['max', 0, ['coalesce', ['get', from], 0]]], 0, 1.5, 30, 2.2, 100, 3.2, 400, 5, 1500, 7] : ['interpolate', ['linear'], ['zoom'], 3, 2, 8, 2.7, 14, 3.6]);
      instance.setPaintProperty('settlements-point', 'circle-opacity', opacity / 100);
      instance.setPaintProperty('regions-line', 'line-color', c.blue);
      instance.setPaintProperty('selected-line', 'line-color', c.blue);
      instance.setPaintProperty('selected-point', 'circle-color', c.blue);
      instance.setPaintProperty('selected-fill', 'fill-color', c.blue);
      (instance.getSource('selected') as maplibregl.GeoJSONSource).setData((selection ? { type: 'FeatureCollection', features: [selection.mode==='settlement'&&placeBoundary?.id===idOf(selection.feature)?placeBoundary.feature:selection.feature] } : empty) as any);
    };
    if (loaded.current) apply(); else instance.once('load', apply);
    if (loaded.current && !busy) updateUrl();
    return () => { instance.off('load', apply); };
  }, [layers, period, opacity, dark, selection, mode, collections,placeBoundary]);

  useEffect(() => {
    if (!selection) { setMembers([]); return; }
    if (selection.mode === 'settlement') { setMembers([selection.feature]); return; }
    // Pinned exporter aggregates use unsimplified source geometry and unique assignment.
    // Recomputing against display polygons would change scientific membership at edges.
    setMembers([]); setAggregateBusy(false);
  }, [selection, collections.settlements]);

  useEffect(() => {
    if (!selection || selection.mode !== 'settlement') return;
    let live = true;
    const getDetail = async () => {
      try {
        const id = idOf(selection.feature); let shard = selection.feature.properties.shard;
        if (!shard) { const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(id)); shard = Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 2); }
        const response = await fetch(`${root}data/settlement-details/${shard}.json`);
        if (!response.ok) throw new Error('detail');
        const data = await response.json();
        if (live) setDetails(data[id] ?? data.records?.[id] ?? null);
      } catch { if (live) setDetailError(true); }
    };
    void getDetail(); return () => { live = false; };
  }, [selection, root]);

  useEffect(()=>{
    setPlaceBoundary(null);setBoundaryStatus('loading');
    if(!selection||selection.mode!=='settlement')return;
    const id=idOf(selection.feature),shard=String(selection.feature.properties.shard||id.slice(0,2));
    let live=true;
    if(!/^[a-f0-9]{2}$/.test(shard)){setBoundaryStatus('missing');return}
    const load=async()=>{
      try{
        if(!polygonCache.current[shard])polygonCache.current[shard]=fetch(`${root}data/settlement-polygons/${shard}.json`).then(response=>{if(!response.ok)throw new Error('boundary');return response.json()}).catch(error=>{delete polygonCache.current[shard];throw error});
        const records=await polygonCache.current[shard],feature=records[id];
        if(!live)return;
        if(!feature||!['Polygon','MultiPolygon'].includes(feature.geometry?.type)||idOf(feature)!==id){setBoundaryStatus('missing');return}
        const boundary={...feature,properties:{...feature.properties,settlementBoundary:true}};
        setPlaceBoundary({id,feature:boundary});setBoundaryStatus('available');
        if(polygonFit.current){polygonFit.current=false;zoomTo(boundary)}
      }catch{if(live)setBoundaryStatus('error')}
    };
    void load();return()=>{live=false};
  },[selection,root]);

  const needle = query.trim().toLocaleLowerCase('ru'), aliasNeedle = searchKey(query);
  const searchable = (f: Feature) => `${titleOf(f)} ${f.properties.sourceName || ''} ${(f.properties.searchAliases || []).join(' ')} ${f.properties.nameRu || ''} ${f.properties.aliases || ''} ${f.properties.region || ''}`;
  const searchRank = (f: Feature) => String(titleOf(f)).toLocaleLowerCase('ru') === needle || searchKey(titleOf(f)) === aliasNeedle ? 0 : String(titleOf(f)).toLocaleLowerCase('ru').startsWith(needle) || searchKey(searchable(f)).startsWith(aliasNeedle) ? 1 : 2;
  const results = needle.length < 2 ? [] : ([['settlements', 'settlement'], ['districts', 'district'], ['regions', 'region']] as const).flatMap(([key, kind]) => collections[key].features.filter(f => searchable(f).toLocaleLowerCase('ru').includes(needle) || key !== 'settlements' && aliasNeedle.length > 1 && searchKey(searchable(f)).includes(aliasNeedle)).sort((a, b) => searchRank(a) - searchRank(b) || Number(b.properties.p21 || 0) - Number(a.properties.p21 || 0)).slice(0, 6).map(feature => ({ mode: kind, feature }))).sort((a, b) => searchRank(a.feature) - searchRank(b.feature)).slice(0, 12);
  const selectedServices = selection ? collections.services.features.filter(f => (f.properties.family === 'schools' ? layers.schools : layers.medical)).filter(f => selection.mode === 'settlement' ? [f.properties.settlementId, f.properties.sourceId, f.properties.originId, f.properties.settlement_id].some(v => String(v) === idOf(selection.feature)) : f.geometry.type === 'Point' && contains(selection.feature, f.geometry.coordinates)) : [];
  const memberCount = selection && selection.mode !== 'settlement' ? selection.feature.properties.count : members.length;
  const comparable = selection && selection.mode !== 'settlement' ? selection.feature.properties.comparableCount : members.filter(f => f.properties.comparable === true && [f.properties.p02, f.properties.p10, f.properties.p21].every(v => number(v) !== null)).length;
  const toggleLayer = (key: keyof Layers) => setLayers(previous => ({ ...previous, [key]: !previous[key] }));
  const researchContext = research || (typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('research') : null);
  const visibleRegistry = registry.filter(meta => !researchContext || meta.researchId === researchContext || customActive.includes(meta.id));
  const enabledRegistry = registry.filter(meta => customActive.includes(meta.id));
  const toggleCustom = (id: string) => setCustomActive(previous => previous.includes(id) ? previous.filter(item => item !== id) : [...previous, id]);
  const share = async () => { updateUrl(); try { await navigator.clipboard.writeText(window.location.href); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { window.prompt('Скопируйте ссылку на карту', window.location.href); } };

  return <section className={`map-workspace ${selection ? 'has-selection' : ''}`} aria-label="Интерактивная карта исследования">
    <div ref={mapElement} className="map-canvas" aria-label="Карта населённых пунктов, регионов и районов" />
    {mapError && <div className="map-failure" role="alert"><strong>Карта недоступна</strong><p>{mapError}</p><a href={`${root}materials/?view=cards`}>Перейти к материалам →</a></div>}
    <div className="map-toolbar">
      <button className={`map-control map-layers-toggle ${panel ? 'active' : ''}`} onClick={() => setPanel(!panel)} aria-expanded={panel}>▦ <span>Слои</span></button>
      <div className="map-search">
        <label className="sr-only" htmlFor="map-search">Поиск места или территории</label>
        <input id="map-search" value={query} onChange={e => { setQuery(e.target.value); setSearchFocus(true); }} onFocus={() => setSearchFocus(true)} onKeyDown={e => { if (e.key === 'Escape') setSearchFocus(false); if (e.key === 'Enter' && results[0]) { select(results[0], true); setSearchFocus(false); setQuery(''); } }} placeholder="Найти место или территорию…" autoComplete="off" />
        {searchFocus && query.trim().length >= 2 && <div className="map-search-results" role="listbox" aria-label="Найденные места">{results.length ? results.map(result => <button key={`${result.mode}-${idOf(result.feature)}`} onClick={() => { select(result, true); setQuery(''); setSearchFocus(false); }}><strong>{titleOf(result.feature)}</strong><small>{selectionLabel(result)}{result.feature.properties.region ? ` · ${result.feature.properties.region}` : ''}{result.mode === 'district' && result.feature.properties.searchAliases?.length ? ` · По записям НП: ${result.feature.properties.searchAliases[0]}` : ''}</small></button>) : <p>{busy||pendingKeys.includes('settlements') ? 'Данные загружаются…' : 'Совпадений нет. Уточните название.'}</p>}</div>}
      </div>
      <div className="map-mode" role="group" aria-label="Что выбирать на карте">{(['settlement', 'district', 'region'] as Mode[]).map(kind => <button key={kind} className={mode === kind ? 'active' : ''} aria-pressed={mode === kind} onClick={() => { cancelPendingSelection();activeMode.current=kind;setMode(kind); if (selection?.mode !== kind) setSelection(null); }}>{kind === 'settlement' ? 'НП' : kind === 'district' ? 'Районы' : 'Регионы'}</button>)}</div>
      <button className="map-control map-share" onClick={share}>{copied ? 'Ссылка скопирована' : 'Поделиться ↗'}</button>
    </div>

    {panel && <aside className="map-layer-panel" aria-label="Слои карты">
      <header><h2>Слои</h2><button onClick={() => setPanel(false)} aria-label="Закрыть слои">×</button></header>
      <fieldset><legend>Население</legend><label className="map-check"><input type="checkbox" checked={layers.population} onChange={() => toggleLayer('population')} /><span className="layer-symbol population-symbol">▪</span><span>{period.includes('-') ? 'Динамика населения' : 'Численность населения'}<small>Переписи · {period.replace('-', '–')}</small></span></label>
        <div className="map-period" role="group" aria-label="Период сравнения">{(['2002-2010', '2010-2021', '2002-2021', '2021'] as Period[]).map(p => <button className={p === period ? 'active' : ''} key={p} onClick={() => setPeriod(p)} aria-pressed={p === period}>{p.replace('-', '–')}</button>)}</div>
        <label className="map-opacity">Непрозрачность <input aria-label="Непрозрачность точек" type="range" min="10" max="100" value={opacity} onChange={e => setOpacity(Number(e.target.value))} /><span>{opacity}%</span></label>
      </fieldset>
      <fieldset><legend>Услуги и связи</legend>{(['schools', 'medical'] as const).map(key => <label className="map-check" key={key}><input type="checkbox" checked={layers[key]} onChange={() => toggleLayer(key)} /><span className="layer-symbol" style={{ color: key === 'schools' ? color(dark).green : color(dark).orange }}>■</span><span>{key === 'schools' ? 'Школы' : 'Медицинская помощь'}<small>НП обслуживания · локальные документы</small></span></label>)}<label className="map-check"><input type="checkbox" checked={layers.links} onChange={() => toggleLayer('links')} /><span className="layer-symbol">↗</span><span>Направления обслуживания<small>Основания — в источниках слоя</small></span></label></fieldset>
      <fieldset><legend>Исследовательские результаты</legend><label className="map-check"><input type="checkbox" checked={layers.centres} onChange={() => toggleLayer('centres')} /><span className="layer-symbol" style={{color:'#7955C5'}}>◎</span><span>Строгие модельные центры<small>{collections.centres.features.length || 197} центров · диагностическое подмножество, не все СГРТ</small></span></label></fieldset><fieldset><legend>Территориальная сетка</legend>{(['districts', 'regions'] as const).map(key => <label className="map-check" key={key}><input type="checkbox" checked={layers[key]} onChange={() => toggleLayer(key)} /><span className="layer-symbol boundary-symbol">□</span><span>{key === 'districts' ? 'Районы и округа' : 'Регионы'}<small>{boundaryStamp(key)}</small>{pendingKeys.includes(key) && <small role="status">Загружаем {key === 'districts' ? 'районы' : 'регионы'}…</small>}</span></label>)}</fieldset>
      <fieldset className="map-research-layers"><legend>Слои исследования</legend>{registryError ? <p>Реестр слоёв недоступен. <button onClick={loadRegistry}>Повторить</button></p> : !visibleRegistry.length ? <p className="map-layer-empty">Опубликованных дополнительных слоёв пока нет.</p> : visibleRegistry.map(meta => <div key={meta.id}><label className="map-check"><input type="checkbox" checked={customActive.includes(meta.id)} onChange={() => toggleCustom(meta.id)} data-layer-id={meta.id} /><span className="layer-symbol">{meta.geometry === 'point' ? '●' : meta.geometry === 'line' ? '╱' : '□'}</span><span>{meta.title}<small>{meta.period} · {meta.unit}{customPending.current.has(meta.id) ? ' · загрузка…' : customCache.current[meta.id] ? ` · ${customCache.current[meta.id].features.length} объектов` : ''}</small></span></label>{customErrors[meta.id] && <p className="map-custom-error" role="alert">Не удалось загрузить слой. <button onClick={() => { customFailure.current.delete(meta.id); setCustomRevision(v => v + 1); }}>Повторить</button></p>}</div>)}</fieldset>
      <p className="map-boundary-note">{siteAssets.boundaryNote} Суммы по границам — пространственный расчёт по базе НП.</p>
      <button className="map-reset" onClick={() => { cancelPendingSelection();activeMode.current='settlement';setLayers(defaultLayers); setCustomActive([]); setPeriod('2002-2021'); setMode('settlement'); setSelection(null); map.current?.flyTo({ center: [88, 59], zoom: 2.6 }); }}>Сбросить настройки ↺</button>
    </aside>}

    {busy && <div className="map-loading" role="status">▦ Загружаем пространственные данные…</div>}
    {Object.keys(errors).length > 0 && <div className="map-data-error" role="alert">Не загружены: {Object.keys(errors).map(k => ({ settlements: 'население', 'settlements-overview':'обзор населения', regions: 'регионы', districts: 'районы', services: 'услуги', links: 'связи', centres: 'центры' })[k]).join(', ')}. <button onClick={loadData}>Повторить</button></div>}
    {!selection && !busy && <div className="map-hint">Выберите {mode === 'settlement' ? 'населённый пункт' : mode === 'district' ? 'район' : 'регион'} на карте — снизу откроются графики</div>}
    {(layers.population || layers.schools || layers.medical || layers.centres || layers.links) && <aside className="map-legend" aria-label="Легенда карты">{layers.population && <><strong>{period.includes('-') ? 'Изменение населения' : 'Население, человек'} · {period.replace('-', '–')}</strong>{period.includes('-') ? <><span><i style={{ background: color(dark).blue }} />Рост более 10%</span><span><i style={{ background: color(dark).orange }} />Сокращение более 10%</span><span><i style={{ background: dark ? '#B0BEDF' : '#A5B5D8' }} />Изменение от −10 до +10%</span><span><i style={{ background: color(dark).gray }} />Нет полного численного ряда</span></> : <><span><i style={{ background: color(dark).blue }} />Размер точки — численность</span><span><i style={{ background: color(dark).gray }} />Нет зачтённого значения</span></>}<small>На обзорном масштабе показаны крупные НП; при приближении — остальные.</small></>}{layers.schools && <span><i className="square" style={{ background: color(dark).green }} />Школьное обслуживание</span>}{layers.medical && <span><i className="square" style={{ background: color(dark).orange }} />Медицинское обслуживание</span>}{layers.centres && <span><i style={{background:'transparent',border:'2px solid #7955C5'}} />Модельные центры · диагностическая выборка</span>}{layers.links && <small>Пунктир — документированная связь. Это не дорожный маршрут и не наблюдённый поток.</small>}</aside>}

    {enabledRegistry.length > 0 && <aside className="map-custom-legend" aria-label="Легенда исследовательских слоёв">{enabledRegistry.map(meta => { const payload = customCache.current[meta.id], stats = payload ? layerStats(payload) : null; return <div key={meta.id}><strong>{meta.title}</strong><span><i style={{background: meta.palette === 'population-change' ? 'linear-gradient(to right,#C65B24,#CED7EC,#244CFF)' : ['categorical','service-type'].includes(meta.palette) ? 'linear-gradient(to right,#244CFF 20%,#16806A 20% 40%,#C65B24 40% 60%,#7955C5 60% 80%,#9C7715 80%)' : undefined}} />{stats ? stats.known ? `${shown(stats.min)} — ${shown(stats.max)} ${meta.unit}` : 'Нет численных значений' : customErrors[meta.id] ? 'Слой недоступен' : 'Загрузка…'}</span><small>{meta.period} · {meta.evidence === 'model' ? 'Модельная оценка' : meta.evidence === 'calculation' ? 'Расчёт' : meta.evidence === 'observation' ? 'Наблюдение' : meta.evidence}{stats ? ` · ${stats.count} объектов, ${stats.known} значений` : ''}</small>{meta.description && <small>{meta.description}</small>}<a href={meta.source?.url} target="_blank" rel="noreferrer">{meta.source?.title || 'Источник'} ↗</a></div>; })}</aside>}
    {selection && <section className={`map-infographic ${collapsed ? 'collapsed' : ''}`} aria-label={`Инфографика: ${titleOf(selection.feature)}`}>
      <div className="map-info-header"><div><span className="map-eyebrow">{selectionLabel(selection)} / {selection.mode === 'settlement' ? selection.feature.properties.region || 'Переписная база' : `Сетка ${selection.feature.properties.epoch} года · ${selection.feature.properties.provider}`}</span><h2>{titleOf(selection.feature)}</h2></div><div className="map-info-actions"><button onClick={() => zoomTo(selection.feature,true)}>Приблизить ↗</button><button onClick={() => setCollapsed(!collapsed)} aria-expanded={!collapsed} aria-label={collapsed ? 'Развернуть графики' : 'Свернуть графики'}>{collapsed ? '⌃' : '⌄'}</button><button onClick={() => { cancelPendingSelection();setSelection(null); updateUrl(null, true); }} aria-label="Закрыть выбранный объект">×</button></div></div>
      {!collapsed && <div className="map-info-body"><div className="map-info-context"><p>{selection.mode === 'settlement' ? 'Население по переписям и сведения об обслуживании.' : 'Пространственная сводка по переписным точкам внутри выбранной границы.'}</p>{selection.mode==='settlement'&&<small data-settlement-boundary={boundaryStatus}>{boundaryStatus==='loading'?'Загружаем контур населённого пункта…':boundaryStatus==='available'?<>Картографический контур НП: {placeBoundary?.feature.properties.source || 'OpenStreetMap'}{placeBoundary?.feature.properties.sourceDate?` · ${String(placeBoundary.feature.properties.sourceDate).split('-').reverse().join('.')}`:''}. {placeBoundary?.feature.properties.sourceUrl&&<a href={placeBoundary.feature.properties.sourceUrl} target="_blank" rel="noopener noreferrer">Источник ↗</a>}</>:boundaryStatus==='missing'?'В подключённом источнике нет однозначно сопоставленного контура этого НП. Показана переписная точка.':'Контур временно недоступен. Показана переписная точка.'}</small>}<dl><div><dt>Переписных точек в базе</dt><dd>{aggregateBusy ? '…' : shown(memberCount)}</dd></div><div><dt>Полных рядов за три переписи</dt><dd>{aggregateBusy ? '…' : `${shown(comparable)} из ${shown(memberCount)}`}</dd></div><div><dt>Услуг в текущем слое</dt><dd>{selectedServices.length ? shown(selectedServices.length) : 'Нет сведений'}</dd></div></dl>{selection.mode !== 'settlement' && <small>Динамика — по НП с полным рядом. Полный численный ряд не доказывает неизменность границ. Это не официальный муниципальный итог.</small>}{selection.mode === 'settlement' && <small>{detailError ? 'Подробный источник временно недоступен.' : details ? `Источник: ${details.source === 'census-population' ? 'Связанная база переписей 2002/2010/2021' : details.source || 'Связанная база переписей'}` : 'Читаем подробные сведения…'}</small>}</div><div className="map-info-visual">{aggregateBusy ? <p role="status">Рассчитываем сводку выбранной территории…</p> : <Charts features={members} selected={selection} dark={dark} />}</div><footer>Переписи 2002 / 2010 / 2021 · Пропуск не равен нулю · <a href={`${root}materials/?kind=method`}>Методология и ограничения ↗</a></footer></div>}
    </section>}
    <div className="map-provenance">{basemapUnavailable ? 'Подложка недоступна; локальные слои сохранены' : 'OpenFreeMap · OpenStreetMap · слои исследования'} · {manifest?.generatedAt ? `Данные: ${new Date(manifest.generatedAt).toLocaleDateString('ru-RU')}` : 'Версионированные данные'} · <a href="https://github.com/ZakBu/russian-settlements-research" target="_blank" rel="noreferrer">Источники и код ↗</a></div>
  </section>;
}
