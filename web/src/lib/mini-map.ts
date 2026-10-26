import type {ZoomTransform} from 'd3-zoom';

type Label=[number,number,string,number|null,number|null];
type Controls={scale:(factor:number)=>void;reset:()=>void;move:(x:number,y:number)=>void};
const svgNS='http://www.w3.org/2000/svg';
const engines=()=>Promise.all([import('d3-selection'),import('d3-zoom')]);
const drawings=new Map<string,Promise<string>>();
const labelSets=new Map<string,Promise<Label[]>>();
let serial=0;
function drawing(url:string){if(!drawings.has(url))drawings.set(url,fetch(url).then(r=>{if(!r.ok)throw Error('SVG');return r.text()}).catch(e=>{drawings.delete(url);throw e}));return drawings.get(url)!}
function labelSet(url:string){if(!labelSets.has(url))labelSets.set(url,fetch(url).then(r=>{if(!r.ok)throw Error('labels');return r.json()}).catch(e=>{labelSets.delete(url);throw e}));return labelSets.get(url)!}
const node=(name:string)=>document.createElementNS(svgNS,name);

export function setupMiniMaps(){
 document.querySelectorAll<HTMLElement>('[data-mini-map]').forEach(root=>{
  if(root.dataset.miniBound)return;root.dataset.miniBound='true';
  const surface=root.querySelector<HTMLElement>('.mini-map-surface')!;
  const toolbar=root.querySelector<HTMLElement>('.mini-map-controls')!;
  const status=root.querySelector<HTMLElement>('.mini-map-status')!;
  const plus=toolbar.querySelector<HTMLButtonElement>('[data-mini-plus]')!,minus=toolbar.querySelector<HTMLButtonElement>('[data-mini-minus]')!,reset=toolbar.querySelector<HTMLButtonElement>('[data-mini-reset]')!;
  let pending:Promise<Controls>|undefined;
  root.setAttribute('role','region');root.classList.add('has-mini-controls');surface.tabIndex=0;toolbar.hidden=false;root.dataset.miniZoom='1';
  const fail=()=>{status.textContent='Не удалось включить приближение. Попробуйте ещё раз.';status.hidden=false;pending=undefined};
  const get=()=>pending??=(async()=>{
   const [[selection,zooming],text]=await Promise.all([engines(),drawing(root.querySelector<HTMLImageElement>('.map-image-light')!.src)]);
   const svg=document.importNode(new DOMParser().parseFromString(text,'image/svg+xml').documentElement,true) as unknown as SVGSVGElement;
   if(svg.tagName.toLowerCase()!=='svg')throw Error('SVG');
   svg.querySelector('style')?.remove();svg.classList.add('mini-map-svg');svg.setAttribute('aria-hidden','true');
   const prefix=`mini-${++serial}-`;
   svg.querySelectorAll('[id]').forEach(el=>{const id=el.id;el.id=prefix+id;svg.querySelectorAll('[href],[fill]').forEach(ref=>{for(const attr of ['href','fill']){const value=ref.getAttribute(attr);if(value===`#${id}`||value===`url(#${id})`)ref.setAttribute(attr,value.replace(`#${id}`,`#${prefix}${id}`))}})});
   const seeds=node('g');seeds.classList.add('mini-map-seeds');svg.querySelectorAll('.overview-city').forEach(el=>seeds.append(el));
   const scene=node('g');scene.classList.add('mini-map-geography');[...svg.children].filter(el=>el.tagName.toLowerCase()!=='defs').forEach(el=>scene.append(el));
   const names=node('g');names.classList.add('mini-map-labels');svg.append(scene,seeds,names);
   let transform=zooming.zoomIdentity,points:Label[]|undefined,loading=false,frame=0;
   const fit=()=>Math.min(surface.clientWidth/960,surface.clientHeight/540);
   const labels=()=>{
    const unit=1/Math.max(.1,fit());
    if(!points){seeds.querySelectorAll<SVGElement>('.overview-city').forEach(el=>{const x=Number(el.dataset.x),y=Number(el.dataset.y),[tx,ty]=transform.apply([x,y]);el.setAttribute('transform',`translate(${tx-x},${ty-y})`)});return}
    seeds.setAttribute('display','none');names.replaceChildren();
    const k=transform.k,minPopulation=k<1.5?1000000:k<3?250000:k<6?50000:k<12?10000:k<24?1000:0;
    root.dataset.miniLabelLevel=String(minPopulation);
    const occupied=new Set<string>();const cellW=45*unit,cellH=20*unit;let count=0;
    for(const [x,y,name,population,change]of points){
     if((population??0)<minPopulation&&count>=8&&!['Москва','Екатеринбург','Владивосток'].includes(name))continue;
     const [tx,ty]=transform.apply([x,y]);if(tx<18||tx>942||ty<42||ty>480)continue;
     const label=name.length>28?name.slice(0,27)+'…':name,width=(label.length*6.7+12)*unit;
     const left=tx+width>942,anchor=left?tx-width:tx+5*unit;
     const cells:string[]=[];for(let cx=Math.floor(anchor/cellW);cx<=Math.floor((anchor+width)/cellW);cx++)for(let cy=Math.floor((ty-9*unit)/cellH);cy<=Math.floor((ty+9*unit)/cellH);cy++)cells.push(`${cx}:${cy}`);
     if(cells.some(key=>occupied.has(key)))continue;cells.forEach(key=>occupied.add(key));
     const group=node('g');group.classList.add('mini-map-place');if(root.dataset.mapVariant==='change')group.setAttribute('data-palette',change===null?'unknown':change< -10?'decline':change>10?'growth':'stable');group.setAttribute('transform',`translate(${tx},${ty})`);
     const dot=node('circle');dot.setAttribute('r',String(2*unit));
     const text=node('text');text.textContent=label;text.setAttribute('x',String((left?-6:6)*unit));text.setAttribute('y',String(4*unit));text.setAttribute('text-anchor',left?'end':'start');text.setAttribute('font-size',String(12*unit));text.setAttribute('stroke-width',String(3.5*unit));
     group.append(dot,text);names.append(group);if(++count>=70)break;
    }
   };
   const resize=()=>{const factor=fit();scene.querySelectorAll<SVGElement>('[stroke-width]').forEach(el=>{const width=el.classList.contains('overview-points')?2.2:.6;el.setAttribute('vector-effect','non-scaling-stroke');el.setAttribute('stroke-width',String(width*factor))});labels()};
   const update=(value:ZoomTransform)=>{
    transform=value;scene.setAttribute('transform',value.toString());root.dataset.miniZoom=value.k.toFixed(2);root.dataset.miniX=value.x.toFixed(1);root.dataset.miniY=value.y.toFixed(1);
    minus.disabled=value.k<=1.001;plus.disabled=value.k>=31.99;reset.disabled=value.k<=1.001;
    scene.querySelector('.overview-land-hatch')?.setAttribute('opacity',value.k>2?'0':'1');
    if(frame)cancelAnimationFrame(frame);frame=requestAnimationFrame(labels);
    if(value.k>1.05&&!points&&!loading){loading=true;status.hidden=false;status.textContent='Загружаем названия…';labelSet(root.dataset.labelsUrl!).then(data=>{points=data;status.hidden=true;labels()}).catch(()=>{status.textContent='Названия пока недоступны. Повторите приближение.'}).finally(()=>loading=false)}
   };
   const zoom=zooming.zoom<SVGSVGElement,unknown>().extent([[0,0],[960,540]]).translateExtent([[0,0],[960,540]]).scaleExtent([1,32])
    .filter(event=>(!event.button||event.type==='wheel')&&(event.type!=='wheel'||event.ctrlKey||event.metaKey)&&(event.type!=='touchstart'||event.touches.length>=2))
    .on('zoom',event=>update(event.transform));
   const selected=selection.select(svg);selected.call(zoom);surface.append(svg);root.classList.add('mini-map-ready');resize();update(transform);
   new ResizeObserver(resize).observe(surface);
   return {scale:factor=>selected.call(zoom.scaleBy,factor),reset:()=>selected.call(zoom.transform,zooming.zoomIdentity),move:(x,y)=>selected.call(zoom.translateBy,x/(fit()*transform.k),y/(fit()*transform.k))};
  })();
  const action=(fn:(api:Controls)=>void)=>{void get().then(fn).catch(fail)};
  plus.addEventListener('click',()=>action(api=>api.scale(1.8)));minus.addEventListener('click',()=>action(api=>api.scale(1/1.8)));reset.addEventListener('click',()=>action(api=>api.reset()));
  surface.addEventListener('keydown',event=>{if(event.ctrlKey||event.metaKey||event.altKey)return;const commands:Record<string,(api:Controls)=>void>={'+':a=>a.scale(1.8),'=':a=>a.scale(1.8),'-':a=>a.scale(1/1.8),'0':a=>a.reset(),Home:a=>a.reset(),ArrowLeft:a=>a.move(70,0),ArrowRight:a=>a.move(-70,0),ArrowUp:a=>a.move(0,70),ArrowDown:a=>a.move(0,-70)};if(commands[event.key]){event.preventDefault();action(commands[event.key])}});
  surface.addEventListener('pointerenter',()=>{void get().catch(fail)},{once:true});surface.addEventListener('focus',()=>{void get().catch(fail)},{once:true});
  if(root.dataset.autoMini==='true'){const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){observer.disconnect();const start=()=>{void get().catch(fail)};if('requestIdleCallback'in window)window.requestIdleCallback(start,{timeout:1200});else setTimeout(start,150)}},{rootMargin:'80px'});observer.observe(surface)}
 });
}
