import {useEffect,useRef,useState} from 'react';
import maplibregl,{type Map as GLMap} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {bounds,colors,empty,type AtlasData,type Collection} from './KrasnodarData';
const population=(p:Record<string,any>)=>Number(p.population2021??p.population_2021??p.population??p.pop2021??0)||0;
function labelImage(text:string,dark:boolean){
 const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d')!;
 ctx.font='500 12px "Golos Text", sans-serif';canvas.width=Math.ceil(ctx.measureText(text).width+14)*2;canvas.height=42;
 ctx.scale(2,2);ctx.font='500 12px "Golos Text", sans-serif';ctx.lineJoin='round';ctx.lineWidth=4;ctx.strokeStyle=dark?'#101c34':'#edf1fb';ctx.fillStyle=dark?'#f4f6ff':'#10265c';ctx.strokeText(text,7,15);ctx.fillText(text,7,15);
 return ctx.getImageData(0,0,canvas.width,canvas.height);
}
function placePopup(properties:Record<string,any>){
 const box=document.createElement('div');box.className='kr-place-popup';const heading=document.createElement('h3');heading.textContent=properties.name||properties.title||'Населённый пункт';box.append(heading);
 const row=(label:string,value:string)=>{const p=document.createElement('p'),strong=document.createElement('strong');strong.textContent=label+': ';p.append(strong,document.createTextNode(value));box.append(p);};
 const number=(v:any)=>v!==null&&v!==undefined&&Number.isFinite(Number(v))?Number(v).toLocaleString('ru-RU',{maximumFractionDigits:1}):'нет сведений';
 row('Население, перепись 2021',number(properties.population2021??properties.population_2021??properties.population??properties.pop2021??null));
 for(const [key,label] of [['time_minutes_base','До центра, базовое время'],['time_minutes_to_core','До контура НП, базовое время'],['time_minutes_to_core_slow','До контура НП, время +30%']])row(label,properties[key]===null||properties[key]===undefined?'нет сведений':`${number(properties[key])} мин`);
 const note=document.createElement('p');note.className='kr-popup-note';note.textContent='Трудовая и учебная зависимость не проверены. Расчётное время не означает наблюдаемую поездку; время до контура не равно времени до рабочего места.';box.append(note);return box;
}
function paperTimePopup(properties:Record<string,any>,sourceUrl?:string){
 const box=document.createElement('div');box.className='kr-place-popup';
 const title=document.createElement('h3');title.textContent=properties.name||'Населённый пункт';box.append(title);
 const period=document.createElement('p');period.textContent=`Опубликованные времена · статья ${properties.tableYear||2019} года. Дата и метод замера не установлены.`;box.append(period);
 for(const [field,label] of [['carMinutes','Автомобиль'],['busMinutes','Автобус'],['railMinutes','Поезд']]){
  const value=properties[field],row=document.createElement('p'),heading=document.createElement('strong');heading.textContent=label+': ';
  const text=value!==null&&value!==undefined&&Number.isFinite(Number(value))?`${Number(value).toLocaleString('ru-RU')} мин`:'нет сведений в таблице';row.append(heading,document.createTextNode(text));box.append(row);
 }
 if(properties.classificationIssue){const issue=document.createElement('p');issue.textContent=String(properties.classificationIssue);box.append(issue);}
 const note=document.createElement('p');note.className='kr-popup-note';note.textContent='Это значения из статьи, а не наш расчёт по сети 2026 года. Координаты НП взяты из переписной основы 2021 года.';box.append(note);
 const url=properties.sourceUrl||sourceUrl;if(typeof url==='string'&&/^https?:\/\//.test(url)){const link=document.createElement('a');link.href=url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Открыть статью и исходную таблицу ↗';box.append(link);}
 return box;
}
export default function KrasnodarMap({data,visible,selected,iso,onSelect,focus=0}:{data:AtlasData;visible:string[];selected?:string;iso:number[];onSelect?:(id:string)=>void;focus?:number}){
 const holder=useRef<HTMLDivElement>(null),mapRef=useRef<GLMap|null>(null);const [ready,setReady]=useState(false),[failure,setFailure]=useState(false);const selectRef=useRef(onSelect);selectRef.current=onSelect;
 const studies=data.manifest.studies;const all=studies.concat(data.manifest.candidate?.geometryUrl?[{...data.manifest.candidate,id:data.manifest.candidate.id||'candidate'}]:[]);
 useEffect(()=>{
  if(!holder.current)return;let disposed=false;const dark=document.documentElement.dataset.theme==='dark';let m:GLMap;
  try{m=new maplibregl.Map({container:holder.current,style:{version:8,sources:{},layers:[{id:'background',type:'background',paint:{'background-color':dark?'#101c34':'#edf1fb'}}]},center:[38.975,45.035],zoom:8,attributionControl:false});}catch{setFailure(true);return;}
  mapRef.current=m;m.addControl(new maplibregl.NavigationControl({showCompass:false}),'top-right');m.addControl(new maplibregl.ScaleControl({unit:'metric'}),'bottom-left');
  const places:Collection={type:'FeatureCollection',features:data.places.features.filter(f=>f.geometry?.type==='Point').sort((a,b)=>population(b.properties)-population(a.properties)).map((f,i)=>({...f,properties:{...f.properties,krRank:i+1,krPopulation:population(f.properties),krLabel:`kr-label-${i}`}}))};
  m.on('load',async()=>{
   const add=(id:string,c:Collection)=>m.addSource(id,{type:'geojson',data:c as any});add('context',data.context);
   m.addLayer({id:'context-water',type:'fill',source:'context',filter:['all',['==',['geometry-type'],'Polygon'],['==',['get','kind'],'river']],paint:{'fill-color':dark?'#204b70':'#bedcee','fill-opacity':.8}});
   m.addLayer({id:'context-river',type:'line',source:'context',filter:['==',['get','kind'],'river'],paint:{'line-color':dark?'#659cc3':'#75b3d4','line-width':2}});
   m.addLayer({id:'context-road',type:'line',source:'context',filter:['==',['get','kind'],'road'],paint:{'line-color':dark?'#6b7790':'#b2bacb','line-width':['interpolate',['linear'],['zoom'],7,.6,12,1.6]}});
   m.addLayer({id:'context-rail',type:'line',source:'context',filter:['in',['get','kind'],['literal',['rail','railway']]],paint:{'line-color':dark?'#8f9cb4':'#8392ae','line-width':1.2,'line-dasharray':[4,3]}});
   m.addLayer({id:'context-core',type:'line',source:'context',filter:['in',['get','kind'],['literal',['core','city_core']]],paint:{'line-color':dark?'#b9caff':'#10265c','line-width':2.2}});
   add('isochrones',data.isochrones);const minutes:any=['to-number',['coalesce',['get','minutes'],['get','threshold'],['get','time_minutes'],['get','contour'],['get','time']]];
   m.addLayer({id:'iso-fill',type:'fill',source:'isochrones',paint:{'fill-color':['match',minutes,30,'#16806a',60,'#244cff',90,'#7955c5','#244cff'],'fill-opacity':.12}});
   m.addLayer({id:'iso-line',type:'line',source:'isochrones',paint:{'line-color':dark?'#a6b9ff':'#244cff','line-width':1.4,'line-dasharray':[3,3]}});
   all.forEach((s,i)=>{const id=`study-${i}`;add(id,data.geometries[s.id]||empty);m.addLayer({id:`${id}-fill`,type:'fill',source:id,paint:{'fill-color':colors[i%colors.length],'fill-opacity':.07}});m.addLayer({id:`${id}-line`,type:'line',source:id,paint:{'line-color':colors[i%colors.length],'line-width':2}});m.addLayer({id:`${id}-point`,type:'circle',source:id,filter:['==',['geometry-type'],'Point'],paint:{'circle-radius':5,'circle-color':colors[i%colors.length],'circle-stroke-color':dark?'#101c34':'#ffffff','circle-stroke-width':2}});m.addLayer({id:`${id}-hit`,type:'line',source:id,paint:{'line-color':colors[i%colors.length],'line-width':14,'line-opacity':0}});});
   add('places',places);
   m.addLayer({id:'places-circle',type:'circle',source:'places',filter:['<=',['get','krRank'],['step',['zoom'],80,9,180,10,400,11,100000]],paint:{'circle-radius':['interpolate',['linear'],['zoom'],7,2.3,12,4],'circle-color':dark?'#d1ddff':'#244cff','circle-stroke-color':dark?'#101c34':'#ffffff','circle-stroke-width':1}});
   await document.fonts.ready;if(disposed)return;
   places.features.forEach(f=>m.addImage(f.properties.krLabel,labelImage(f.properties.name||f.properties.title||'',dark),{pixelRatio:2}));
   m.addLayer({id:'places-label',type:'symbol',source:'places',filter:['<=',['get','krRank'],['step',['zoom'],20,9,45,10,100,11,250,12,100000]],layout:{'icon-image':['get','krLabel'],'icon-anchor':'left','icon-offset':[5,0],'icon-allow-overlap':false,'icon-ignore-placement':false,'icon-padding':4,'symbol-sort-key':['-',0,['get','krPopulation']]}});
   m.on('click',e=>{
    const paperPoint=m.queryRenderedFeatures(e.point,{layers:all.flatMap((_,i)=>[`study-${i}-point`])})[0];
    if(paperPoint?.geometry.type==='Point'){const i=Number(paperPoint.layer.id.split('-')[1]);selectRef.current?.(all[i].id);new maplibregl.Popup({maxWidth:'310px'}).setLngLat((paperPoint.geometry as any).coordinates).setDOMContent(paperTimePopup(paperPoint.properties,all[i].sourceUrl)).addTo(m);return;}
    const place=m.queryRenderedFeatures(e.point,{layers:['places-circle','places-label']})[0];
    if(place?.geometry.type==='Point'){new maplibregl.Popup({maxWidth:'290px'}).setLngLat((place.geometry as any).coordinates).setDOMContent(placePopup(place.properties)).addTo(m);return;}
    const hits=m.queryRenderedFeatures(e.point,{layers:all.flatMap((_,i)=>[`study-${i}-point`,`study-${i}-hit`,`study-${i}-fill`])});const hit=hits.find(h=>h.layer.id.endsWith('-point'))||hits.find(h=>h.layer.id.endsWith('-hit'))||hits[0];if(hit){const i=Number(hit.layer.id.split('-')[1]);selectRef.current?.(all[i].id);}
   });
   for(const layer of ['places-circle','places-label',...all.flatMap((_,i)=>[`study-${i}-fill`,`study-${i}-hit`,`study-${i}-point`])]){m.on('mouseenter',layer,()=>m.getCanvas().style.cursor='pointer');m.on('mouseleave',layer,()=>m.getCanvas().style.cursor='');}
   const box=bounds(all.map(s=>data.geometries[s.id]||empty));if(box)m.fitBounds(box,{padding:38,duration:0});m.once('idle',()=>holder.current?.setAttribute('data-ready','true'));setReady(true);
  });
  const resize=new ResizeObserver(()=>{holder.current?.setAttribute('data-ready','false');m.resize();m.once('idle',()=>holder.current?.setAttribute('data-ready','true'));});resize.observe(holder.current);
  const theme=()=>{if(!m.isStyleLoaded())return;const d=document.documentElement.dataset.theme==='dark';m.setPaintProperty('background','background-color',d?'#101c34':'#edf1fb');m.setPaintProperty('context-road','line-color',d?'#6b7790':'#b2bacb');m.setPaintProperty('context-river','line-color',d?'#659cc3':'#75b3d4');m.setPaintProperty('context-water','fill-color',d?'#204b70':'#bedcee');m.setPaintProperty('context-core','line-color',d?'#b9caff':'#10265c');m.setPaintProperty('places-circle','circle-color',d?'#d1ddff':'#244cff');places.features.forEach(f=>{if(m.hasImage(f.properties.krLabel))m.updateImage(f.properties.krLabel,labelImage(f.properties.name||f.properties.title||'',d));});};
  window.addEventListener('atlas-theme',theme);return()=>{disposed=true;resize.disconnect();window.removeEventListener('atlas-theme',theme);m.remove();setReady(false);};
 },[data]);
 useEffect(()=>{const m=mapRef.current;if(!ready||!m)return;all.forEach((s,i)=>{const show=visible.includes(s.id);for(const suffix of ['fill','line','hit','point'])m.setLayoutProperty(`study-${i}-${suffix}`,'visibility',show?'visible':'none');m.setPaintProperty(`study-${i}-line`,'line-width',selected===s.id?3.5:1.7);m.setPaintProperty(`study-${i}-fill`,'fill-opacity',selected===s.id?.15:.045);});const expr:any=['in',['to-number',['coalesce',['get','minutes'],['get','threshold'],['get','time_minutes'],['get','contour'],['get','time']]],['literal',iso]];m.setFilter('iso-fill',expr);m.setFilter('iso-line',expr);},[ready,visible.join(','),selected,iso.join(',')]);
 useEffect(()=>{const m=mapRef.current;if(!ready||!m)return;const b=bounds((selected&&visible.length===1?[selected]:visible).map(id=>data.geometries[id]||empty));if(b)m.fitBounds(b,{padding:40,duration:window.matchMedia('(prefers-reduced-motion: reduce)').matches?0:400});},[ready,focus]);
 return <div className="kr-map-canvas" ref={holder} role="region" aria-label="Интерактивная карта границ Краснодарской агломерации">{failure&&<p className="kr-map-failure">Карта WebGL недоступна. Выберите исследование в списке: источник и описание доступны ниже.</p>}<span className="kr-map-registration" aria-hidden="true">45° с. ш. / 39° в. д.</span><a className="kr-map-attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap · геометрия источников</a></div>;
}
