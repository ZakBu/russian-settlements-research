import type {Map as LibreMap,LayerSpecification,StyleSpecification} from 'maplibre-gl';

const STYLE_URL='https://tiles.openfreemap.org/styles/liberty';
const SOURCE_ID='context-vector';
const OVERVIEW_ID='context-transport-overview';
const GLYPHS='https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf';
const ATTRIBUTION='<a href="https://openfreemap.org">OpenFreeMap</a> · <a href="https://openmaptiles.org/">© OpenMapTiles</a> · <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap</a>';
const russianName=['coalesce',['get','name:ru'],['get','name'],''];

export type ContextBasemap={setTheme(dark:boolean):void;dispose():void};

/** Reuse OpenFreeMap's cartography; research overlays stay independent of its availability. */
export async function addContextBasemap(map:LibreMap,options:{base?:string;dark?:boolean;onStatus?:(available:boolean)=>void}={}):Promise<ContextBasemap>{
 let dark=!!options.dark,disposed=false,glyphFailed=false,lastStatus:boolean|undefined;
 const controller=new AbortController(),added:string[]=[],families=new Map<string,string>();
 const report=(available:boolean)=>{if(!disposed&&lastStatus!==available){lastStatus=available;options.onStatus?.(available)}};
 const timeout=setTimeout(()=>controller.abort(),10000);
 const safeStyle=()=>{try{return map.getStyle()}catch{return undefined}};
 const available=()=>!disposed&&!!safeStyle();
 const onError=(event:any)=>{if(/glyph|tiles\.openfreemap\.org\/fonts/i.test(event.error?.message||'')){glyphFailed=true;report(false)}else if(event.sourceId===SOURCE_ID)report(false)};
 const onData=(event:any)=>{if(!glyphFailed&&event.sourceId===SOURCE_ID&&event.sourceDataType==='content')report(true)};
 function setTheme(value:boolean){
  dark=value;if(!available())return;
  const colors=dark?{water:'#142842',green:'#142b2b',land:'#18233a',rail:'#9b93b8',road:'#64758e',casing:'#25354d',urban:'#23344e',building:'#435a78',buildingLine:'#6d839f',boundary:'#566b89',text:'#b2c2df',halo:'#080f24'}:{water:'#d8eaff',green:'#e5eee7',land:'#edf0f7',rail:'#817793',road:'#bfa386',casing:'#f7f8fc',urban:'#dbe1ed',building:'#bdcadc',buildingLine:'#99adc8',boundary:'#a3afc6',text:'#687b9e',halo:'#f4f6ff'};
  for(const id of added){const layer=map.getLayer(id);if(!layer)continue;const sourceLayer=families.get(id)||'';
   if(layer.type==='fill'){
    const fill=sourceLayer==='water'?colors.water:sourceLayer==='building'?colors.building:id==='context-landuse_residential'?colors.urban:/landcover|park/.test(sourceLayer)?colors.green:colors.land;
    map.setPaintProperty(id,'fill-color',fill);map.setPaintProperty(id,'fill-outline-color',sourceLayer==='building'?colors.buildingLine:fill);
   }else if(layer.type==='line')map.setPaintProperty(id,'line-color',sourceLayer==='waterway'?colors.water:sourceLayer==='boundary'?colors.boundary:/major_rail/.test(id)?colors.rail:id.endsWith('_casing')?colors.casing:colors.road);
   else if(layer.type==='symbol'){map.setPaintProperty(id,'text-color',colors.text);map.setPaintProperty(id,'text-halo-color',colors.halo)}
  }
 }
 function dispose(){
  if(disposed)return;disposed=true;controller.abort();clearTimeout(timeout);
  map.off('error',onError);map.off('sourcedata',onData);map.off('remove',dispose);
  if(!safeStyle())return;
  try{for(const id of [...added].reverse())if(map.getLayer(id))map.removeLayer(id);if(map.getSource(SOURCE_ID))map.removeSource(SOURCE_ID);if(map.getSource(OVERVIEW_ID))map.removeSource(OVERVIEW_ID)}catch{/* Removal can precede the asynchronous style response. */}
 }
 map.on('remove',dispose);map.on('error',onError);map.on('sourcedata',onData);
 if(available()){
  const before=safeStyle()?.layers.find(layer=>layer.type!=='background')?.id;
  map.addSource(OVERVIEW_ID,{type:'geojson',data:`${options.base||'/'}data/context-transport-overview.geojson`,attribution:'<a href="https://www.naturalearthdata.com/">Natural Earth</a>'});
  for(const kind of ['road','rail']){
   const id=kind==='rail'?'context-overview-major_rail':'context-overview-motorway';
   map.addLayer({id,type:'line',source:OVERVIEW_ID,maxzoom:kind==='rail'?6:4,filter:['==',['get','kind'],kind],paint:{'line-color':kind==='rail'?'#817793':'#bfa386','line-width':kind==='rail'?.8:1.1,...(kind==='rail'?{'line-dasharray':[4,2]}:{})}} as LayerSpecification,before);added.push(id);families.set(id,'transportation');
  }
  setTheme(dark);
 }

 try{
  const response=await fetch(STYLE_URL,{signal:controller.signal});if(!response.ok)throw Error(`OpenFreeMap: ${response.status}`);
  const style=await response.json() as StyleSpecification;
  if(style.version!==8||!style.sources.openmaptiles||!Array.isArray(style.layers))throw Error('Invalid context map style');
  if(!available())return {setTheme,dispose};
  map.setGlyphs(GLYPHS);
  map.addSource(SOURCE_ID,{type:'vector',url:'https://tiles.openfreemap.org/planet',attribution:ATTRIBUTION});
  // Async insertion below local research layers, preserving their selection and data.
  const before=safeStyle()?.layers.find(layer=>layer.type!=='background')?.id;
  for(const original of style.layers){
   const layer:any=structuredClone(original),family=layer['source-layer'];
   if(layer.source!=='openmaptiles'||!['fill','line','symbol'].includes(layer.type))continue;
   if(layer.type==='fill'&&!['water','landcover','landuse','park','building'].includes(family))continue;
   if(layer.type==='line'&&!['transportation','waterway','boundary'].includes(family))continue;
   if(layer.type==='line'&&(/hatching/.test(layer.id)||/rail/.test(layer.id)&&!/major_rail/.test(layer.id)))continue;
   if(layer.type==='symbol'&&!(family==='place'||family==='water_name'||family==='waterway'||layer.id.startsWith('highway-name-')))continue;
   if(layer.id==='label_state')continue; // Administrative names come from the research grid.
   if(layer.paint?.['fill-pattern']||layer.paint?.['line-pattern'])continue;
   layer.id=`context-${layer.id}`;layer.source=SOURCE_ID;
   if(family==='place'){
    if(layer.id==='context-label_city_capital')layer.minzoom=2.3;
    else if(!layer.id.startsWith('context-label_country'))layer.minzoom=Math.max(layer.minzoom||0,4);
   }
   if(family==='building'){layer.minzoom=13;delete layer.maxzoom;layer.paint['fill-opacity']=['interpolate',['linear'],['zoom'],13,.78,14,.9]}
   if(layer.id==='context-landuse_residential'){delete layer.maxzoom;layer.paint['fill-opacity']=['interpolate',['linear'],['zoom'],8,.45,11,.7,13,.35,15,.18]}
   if(family==='transportation'){
    const major=/motorway|trunk_primary/.test(layer.id),regional=/secondary_tertiary/.test(layer.id);
    const rail=/major_rail/.test(layer.id);
    layer.minzoom=rail?6:major&&!/link/.test(layer.id)?4:Math.max(layer.minzoom||0,regional?8:12);
    if(rail){layer.paint['line-width']=['interpolate',['linear'],['zoom'],3,.7,8,1,14,1.4];layer.paint['line-dasharray']=[4,2]}
    else if(major&&!/casing|link/.test(layer.id))layer.paint['line-width']=['interpolate',['linear'],['zoom'],3,.8,6,1.2,12,2.5,16,5];
   }
   if(layer.type==='symbol'){
    layer.layout={...layer.layout,'text-field':russianName,'text-font':['Noto Sans Regular'],'text-allow-overlap':false,'text-ignore-placement':false};
    // Text-only places use the ready style's rank/collision rules, without loading icon sprites.
    for(const key of Object.keys(layer.layout))if(key.startsWith('icon-'))delete layer.layout[key];
    layer.paint={...layer.paint,'text-halo-width':1.5,'text-halo-blur':.3};
    if(family==='water_name')layer.minzoom=Math.max(layer.minzoom||0,3);
   }
   map.addLayer(layer as LayerSpecification,before);added.push(layer.id);families.set(layer.id,family);
  }
  setTheme(dark);
 }catch{if(!disposed)report(false)}finally{clearTimeout(timeout)}
 return {setTheme,dispose};
}
