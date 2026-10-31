export type Geometry = {type:string;coordinates?:any;geometries?:Geometry[]};
export type Feature = {type:'Feature';geometry:Geometry|null;properties:Record<string,any>};
export type Collection = {type:'FeatureCollection';features:Feature[]};
export type Study = {id:string;title:string;year?:number|string;authors?:string|string[];sourceUrl?:string;summary?:string;geometryKind?:string;geometryUrl?:string;limitations?:string[];sourceVersion?:string;[key:string]:any};
export type Manifest = {studies:Study[];isochrones?:{url?:string;geometryUrl?:string;thresholds?:number[];summary?:string;limitations?:string[];[key:string]:any};candidate?:Study;statistics?:any;context?:{url?:string;[key:string]:any};places?:{url?:string;[key:string]:any};[key:string]:any};
export type AtlasData = {manifest:Manifest;geometries:Record<string,Collection>;isochrones:Collection;isochroneVariants:Record<string,Collection>;context:Collection;places:Collection;errors:string[]};
export const empty:Collection={type:'FeatureCollection',features:[]};
export const colors=['#244cff','#16806a','#c65b24','#7955c5','#9c7715','#bc4f71','#008a9d','#695748','#617d2b'];
export const author=(s:Study)=>[Array.isArray(s.authors)?s.authors.join(', '):s.authors,s.year].filter(Boolean).join(' · ');
export function asset(base:string,path:string){if(/^https?:\/\//.test(path))return path;if(path.startsWith(base+'data/'))return path;return `${base}${path.replace(/^\//,'').replace(/^public\//,'').replace(/^(?!data\/)/,'data/krasnodar/')}`;}
function collection(value:any):Collection{if(value?.type==='FeatureCollection')return value;if(value?.type==='Feature')return {type:'FeatureCollection',features:[value]};if(value?.coordinates)return {type:'FeatureCollection',features:[{type:'Feature',geometry:value,properties:{}}]};return empty;}
export async function loadAtlas(base:string,signal?:AbortSignal):Promise<AtlasData>{
 const response=await fetch(`${base}data/krasnodar/manifest.json`,{signal});if(!response.ok)throw new Error('Не удалось загрузить каталог границ. Попробуйте обновить страницу.');
 const manifest:Manifest=await response.json();const errors:string[]=[];
 const read=async(url?:string)=>{if(!url)return empty;try{const r=await fetch(asset(base,url),{signal});if(!r.ok)throw Error();return collection(await r.json());}catch(e){if(signal?.aborted)throw e;errors.push(url);return empty;}};
 const geometries:Record<string,Collection>={};await Promise.all((manifest.studies||[]).map(async s=>{geometries[s.id]=await read(s.geometryUrl||s.url);}));
 if(manifest.candidate?.geometryUrl)geometries[manifest.candidate.id||'candidate']=await read(manifest.candidate.geometryUrl);
 if(manifest.candidate?.robustGeometryUrl)geometries[(manifest.candidate.id||'candidate')+'-robust']=await read(manifest.candidate.robustGeometryUrl);
 const [isochrones,context,loadedPlaces]=await Promise.all([read(manifest.isochrones?.url||manifest.isochrones?.geometryUrl),read(manifest.context?.url||manifest.contextUrl),read(manifest.places?.url||manifest.placesUrl)]);
 const isochroneVariants:Record<string,Collection>={};await Promise.all((manifest.isochrones?.variants||[]).map(async(v:any)=>{isochroneVariants[v.id]=await read(v.url);}));
 const places=loadedPlaces.features.length?loadedPlaces:{type:'FeatureCollection' as const,features:manifest.studies.filter(s=>s.geometryKind==='point').flatMap(s=>(geometries[s.id]||empty).features.filter(f=>f.geometry?.type==='Point'))};
 return {manifest,geometries,isochrones,isochroneVariants,context,places,errors};
}
export function positions(geometry:Geometry|null):number[][]{if(!geometry)return [];if(geometry.type==='GeometryCollection')return (geometry.geometries||[]).flatMap(positions);const all:number[][]=[];const visit=(a:any)=>{if(Array.isArray(a)&&typeof a[0]==='number'&&typeof a[1]==='number')all.push(a);else if(Array.isArray(a))a.forEach(visit);};visit(geometry.coordinates);return all;}
export function bounds(collections:Collection[]):[[number,number],[number,number]]|undefined{const p=collections.flatMap(c=>c.features.flatMap(f=>positions(f.geometry)));if(!p.length)return;return [[Math.min(...p.map(x=>x[0])),Math.min(...p.map(x=>x[1]))],[Math.max(...p.map(x=>x[0])),Math.max(...p.map(x=>x[1]))]];}
export const minute=(f:Feature)=>Number(f.properties.minutes??f.properties.threshold??f.properties.time_minutes??f.properties.contour??f.properties.time);
export function statsRows(value:any):{label:string;value:string;unit?:string;note?:string}[]{if(Array.isArray(value))return value.filter(v=>v&&typeof v==='object'&&(v.label||v.title)&&v.value!==undefined).map(v=>({label:v.label||v.title,value:String(v.value),unit:v.unit,note:v.note||v.source}));if(Array.isArray(value?.items))return statsRows(value.items);return [];}
