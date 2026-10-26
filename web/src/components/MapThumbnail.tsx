import {useEffect,useRef,useState} from 'react';
import {geoConicEqualArea,geoGraticule,geoPath} from 'd3-geo';
type Point=[number,number,number|null];
let shared:Promise<{points:Point[];land:any}>|undefined;
const cities=[{name:'Москва',coordinates:[37.6173,55.7558] as [number,number]}, {name:'Екатеринбург',coordinates:[60.5975,56.8389] as [number,number]}, {name:'Владивосток',coordinates:[131.8855,43.1155] as [number,number]}];
export default function MapThumbnail({base,caption='Распределение населённых пунктов',large=false,variant='distribution',hero=false}:{base:string;caption?:string;large?:boolean;variant?:'distribution'|'change';hero?:boolean}){
 const ref=useRef<HTMLCanvasElement>(null);const [error,setError]=useState(false);
 useEffect(()=>{let active=true;let observer:ResizeObserver|undefined;let dispose=()=>{};const canvas=ref.current;if(!canvas)return;
 const draw=({points,land}:{points:Point[];land:any})=>{
  if(!active)return;const c=canvas.getContext('2d');if(!c)return;
  const {width:w,height:h}=canvas.getBoundingClientRect();if(!w||!h)return;
  const dpr=Math.min(devicePixelRatio||1,2);canvas.width=w*dpr;canvas.height=h*dpr;c.scale(dpr,dpr);
  const dark=document.documentElement.dataset.theme==='dark';const blue=dark?'#8da8ff':'#244cff';const orange=dark?'#ffaa76':'#f17f4f';
  // One scale for both axes; rotation keeps Chukotka contiguous across 180°.
  const projection=geoConicEqualArea().rotate([-105,0]).parallels([50,70]);const vertices:any[]=[];
  for(const f of land.features)for(const ring of f.geometry.coordinates)for(const coordinate of ring)vertices.push(coordinate);
  projection.fitExtent([[16,large?46:22],[w-16,h-(large?58:32)]],{type:'MultiPoint',coordinates:vertices});const path=geoPath(projection,c);
  // Graticule and pale land stippling are reference artwork, never population.
  c.strokeStyle=blue;c.lineWidth=.55;c.globalAlpha=.16;c.setLineDash([1,5]);c.beginPath();path(geoGraticule().step([20,10]).extent([[18,40],[191,84]])());c.stroke();c.setLineDash([]);
  c.save();c.beginPath();path(land);c.clip();c.fillStyle=blue;c.globalAlpha=dark?.12:.07;c.fillRect(0,0,w,h);c.globalAlpha=dark?.35:.24;
  const step=large?5:4;for(let y=12;y<h;y+=step)for(let x=8;x<w;x+=step){c.beginPath();c.arc(x,y,.55,0,Math.PI*2);c.fill()}c.restore();
  c.globalAlpha=.3;c.strokeStyle=blue;c.lineWidth=.5;c.beginPath();path(land);c.stroke();
  // Subsample for legibility, retaining marks at their real projected coordinates.
  const occupied=new Set<string>();const spacing=large?3:2.3;
  for(const [lon,lat,change]of points){const point=projection([lon,lat]);if(!point)continue;const [x,y]=point;if(x<0||x>w||y<0||y>h)continue;
   const key=`${Math.floor(x/spacing)}:${Math.floor(y/spacing)}`;if(occupied.has(key))continue;occupied.add(key);
   c.fillStyle=variant==='change'?(change===null?(dark?'#a1aed0':'#8390b3'):change< -10?orange:change>10?blue:(dark?'#c5d2ff':'#a7bcff')):blue;
   c.globalAlpha=.92;const size=large?1.25:.9;c.beginPath();c.arc(x,y,size,0,Math.PI*2);c.fill();
  }
  c.globalAlpha=1;
  if(large&&w>430)for(const [i,city]of cities.entries()){
   const pos=projection(city.coordinates);if(!pos)continue;const [x,y]=pos;c.fillStyle=dark?'#111d37':'#f4f6ff';c.strokeStyle=blue;c.lineWidth=1.4;c.beginPath();c.arc(x,y,4,0,Math.PI*2);c.fill();c.stroke();
   const dx=i===2?-16:16,dy=i<2?30:-32;c.globalAlpha=.6;c.lineWidth=.7;c.beginPath();c.moveTo(x+Math.sign(dx)*5,y);c.lineTo(x+dx,y+dy);c.lineTo(x+dx+(i===2?-60:60),y+dy);c.stroke();c.globalAlpha=1;
   c.font='11px "IBM Plex Mono", monospace';c.textAlign=i===2?'right':'left';c.fillStyle=blue;c.fillText(city.name,x+dx,y+dy-6);
   if(hero){c.font='9px "IBM Plex Mono", monospace';c.globalAlpha=.8;c.fillText(`${city.coordinates[1].toFixed(2)}° N / ${city.coordinates[0].toFixed(2)}° E`,x+dx,y+dy+11);c.globalAlpha=1}
  }
 };
 const url=base.replace(/\/$/,'');shared??=Promise.all([fetch(`${url}/data/settlements-preview.json`).then(r=>{if(!r.ok)throw Error('points unavailable');return r.json()}),fetch(`${url}/data/country-preview.geojson`).then(r=>{if(!r.ok)throw Error('outline unavailable');return r.json()})]).then(([points,land])=>({points,land}));
 shared.then(data=>{if(!active)return;draw(data);observer=new ResizeObserver(()=>draw(data));observer.observe(canvas);const listener=()=>draw(data);window.addEventListener('atlas-theme',listener);dispose=()=>window.removeEventListener('atlas-theme',listener)}).catch(()=>{if(active)setError(true)});
 return()=>{active=false;observer?.disconnect();dispose()};},[base,large,variant,hero]);
 return <div className={`cartographic-preview ${large?'is-large':''} ${hero?'is-hero':''}`}>
  <div className="map-plate-heading" aria-hidden="true"><span>РОССИЯ / {variant==='change'?'2002 — 2021':'ПЕРЕПИСНАЯ ОСНОВА'}</span><span className="map-registration">＋</span></div>
  {error?<p className="map-preview-error">Пространственный слой пока недоступен. Описание и источники доступны в материале.</p>:<canvas ref={ref} className="pixel-map" aria-label={`${caption}. Коническая равновеликая проекция Альберса. ${variant==='change'?'Цвет показывает изменение численности в сопоставимых рядах 2002–2021 годов.':''}`} role="img"/>}
  <div className="map-plate-key">{variant==='change'?<><span><i className="key-dot decline"/>Снижение &gt;10%</span><span><i className="key-dot stable"/>±10%</span><span><i className="key-dot growth"/>Рост &gt;10%</span><span><i className="key-dot unknown"/>Нет ряда</span></>:<span><i className="key-dot growth"/>Населённые пункты</span>}</div>
  <span className="mini-map-label">{large?'Пространственная выборка · фон — контур территории':'Выборка НП · справочный контур'}</span>
 </div>;
}
