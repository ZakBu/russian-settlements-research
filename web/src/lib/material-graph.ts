import researchRegistry from '../../content/research.json';

export type MaterialGraphNode = {
 id:string;title:string;url:string;kind:string;summary:string;researchId?:string;
};
export type MaterialGraphEdge = {
 source:string;target:string;type:'reference'|'supersedes'|'dataset'|'hierarchy';label?:string;
};
export type MaterialGraphInput = {nodes:MaterialGraphNode[];edges:MaterialGraphEdge[]};
const containers=new WeakMap<HTMLElement,{dispose?:()=>void}>();

/** Loaded only when a reader requests the graph; articles remain ordinary links. */
export async function renderMaterialGraph(
 container:HTMLElement,
 input:MaterialGraphInput,
 onSelect:(id:string)=>void,
):Promise<{dispose():void;resize():void}>{
 // Filtering can start another lazy import before this call finishes loading.
 // A stale invocation must never initialise or dispose the newer chart.
 containers.get(container)?.dispose?.();
 const lease:{dispose?:()=>void}={};containers.set(container,lease);
 const [echarts,{GraphChart},{SVGRenderer},{LegendComponent}]=await Promise.all([
  import('echarts/core'),import('echarts/charts'),import('echarts/renderers'),import('echarts/components'),
 ]);
 if(containers.get(container)!==lease)return {dispose(){},resize(){}};
 echarts.use([GraphChart,SVGRenderer,LegendComponent]);
 const chart=echarts.init(container,undefined,{renderer:'svg'});
 const ids=new Set(input.nodes.map(node=>node.id));
 const edges=input.edges.filter(edge=>ids.has(edge.source)&&ids.has(edge.target));
 const degrees=new Map<string,number>();
 for(const edge of edges){
  degrees.set(edge.source,(degrees.get(edge.source)||0)+1);
  degrees.set(edge.target,(degrees.get(edge.target)||0)+1);
 }
 const media=matchMedia('(prefers-reduced-motion: reduce)');
 const shapes:Record<string,string>={finding:'circle',method:'diamond',note:'roundRect',correction:'rect',dataset:'triangle'};
 let disposed=false;
 function render(){
  if(disposed)return;
  const css=getComputedStyle(document.documentElement);
  const color=(key:string,fallback:string)=>css.getPropertyValue(key).trim()||fallback;
  const ink=color('--ink','#141f55'),blue=color('--blue','#2545ff');
  const muted=color('--muted','#596790'),line=color('--line','#b4c0fa');
  const background=color('--bg','#f5f6ff');
  const dark=document.documentElement.dataset.theme==='dark';
  const palette:Record<string,string>={
   population:color('--collection-population',dark?'#9caeff':'#2545ff'),
   sgrt:color('--collection-sgrt',dark?'#61d0bc':'#007f73'),
   ecommerce:color('--collection-ecommerce',dark?'#ffb38a':'#b74b1d'),
  };
  const collections=researchRegistry.filter(research=>input.nodes.some(node=>node.researchId===research.id)).sort((a,b)=>a.order-b.order);
  const categories=collections.map(research=>({name:research.title,itemStyle:{color:palette[research.id]||blue}}));
  const categoryById=new Map(collections.map((research,index)=>[research.id,index]));
  chart.setOption({
   animation:false,
   backgroundColor:'transparent',
   textStyle:{fontFamily:'Golos Text, sans-serif',color:ink},
   legend:{selectedMode:false,top:0,left:0,right:0,itemWidth:11,itemHeight:11,itemGap:14,textStyle:{color:ink,fontFamily:'Golos Text, sans-serif',fontSize:11},data:categories.map(category=>category.name)},
   series:[{
    type:'graph',
    // No continuous movement: force settles before drawing; reduced motion uses a fixed circle.
    layout:media.matches?'circular':'force',
    force:{repulsion:260,edgeLength:[90,160],gravity:.08,layoutAnimation:false},
    circular:{rotateLabel:false},
    roam:true,scaleLimit:{min:.5,max:3},draggable:!media.matches,
    left:55,right:55,top:categories.length?75:55,bottom:55,
    categories,
    data:input.nodes.map(node=>({
     id:node.id,name:node.title,category:categoryById.get(node.researchId||''),
     symbol:shapes[node.kind]||'circle',
     symbolSize:Math.min(34,17+Math.sqrt(degrees.get(node.id)||0)*4),
     itemStyle:{color:palette[node.researchId||'']||blue,borderColor:background,borderWidth:2},
    })),
    links:edges.map(edge=>({
     source:edge.source,target:edge.target,
     name:edge.label||({reference:'Ссылается на',supersedes:'Уточняет или заменяет',dataset:'Использует данные',hierarchy:'Содержит раздел'}[edge.type]),
     lineStyle:{
      color:edge.type==='supersedes'?blue:edge.type==='hierarchy'?muted:line,
      type:edge.type==='dataset'?'dotted':edge.type==='supersedes'?'dashed':'solid',
      width:edge.type==='supersedes'||edge.type==='hierarchy'?2:1.2,opacity:edge.type==='hierarchy'?.6:.8,curveness:edge.type==='hierarchy'?0:.08,
     },
    })),
    edgeSymbol:['none','arrow'],edgeSymbolSize:[0,6],
    label:{show:true,position:'bottom',distance:8,color:muted,fontSize:11,width:135,overflow:'truncate'},
    emphasis:{
     focus:'adjacency',
     label:{show:true,color:ink,fontWeight:600,width:220,overflow:'break'},
     lineStyle:{color:blue,width:2,opacity:1},
    },
    blur:{itemStyle:{opacity:.25},lineStyle:{opacity:.15},label:{opacity:.25}},
    select:{itemStyle:{borderColor:ink,borderWidth:3}},
    selectedMode:'single',
   }],
  },true);
 }
 function resize(){if(!disposed)chart.resize()}
 chart.on('click',params=>{
  if(params.dataType!=='node')return;
  const id=(params.data as {id?:string}|undefined)?.id;
  if(id&&ids.has(id))onSelect(id);
 });
 try{render()}catch(error){chart.dispose();if(containers.get(container)===lease)containers.delete(container);throw error}
 const observer=new ResizeObserver(resize);
 observer.observe(container);
 window.addEventListener('atlas-theme',render);
 media.addEventListener('change',render);
 const handle={
  resize,
  dispose(){
   if(disposed)return;
   disposed=true;observer.disconnect();
   window.removeEventListener('atlas-theme',render);
   media.removeEventListener('change',render);
   chart.dispose();
   if(containers.get(container)===lease)containers.delete(container);
  },
 };
 lease.dispose=handle.dispose;
 return handle;
}
