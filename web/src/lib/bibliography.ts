import {renderDocument, type DocumentOptions} from './document.ts';

/** Optional factual description, never inferred from a commit date or URL. */
export type BibliographicFields={authors?:string|string[];year?:number|string;publisher?:string;place?:string;journal?:string;volume?:number|string;issue?:number|string;pages?:string;doi?:string;accessed?:string;referenceId?:string};
export type PublicationSource=BibliographicFields&{title:string;url:string;release?:string};
export type PublicationDataset=PublicationSource&{id:string};
export type PublicationVisual={id:string;title:string;template:string;datasetId:string};
export type LiteratureRecord=BibliographicFields&{id:string;title:string;url?:string;reading_url?:string};
export type PublicationMaterial={id:string;body:string;sources:PublicationSource[];visualIds:string[];datasetIds?:string[]};
export type BibliographyEntry={id:string;number:number;url:string;title:string;text:string};
export type FigureInfo={id:string;kind:'figure'|'table'|'link';number?:number;title:string;label:string;sourceText:string;sourceTitle?:string;sourceNumber?:number;sourceUrl?:string;sourceId?:string;authored:boolean};
export type PublicationOptions={visuals:readonly PublicationVisual[];datasets:readonly PublicationDataset[];literature?:readonly LiteratureRecord[];basePath?:string;materialIds?:readonly string[]};

const escapeHtml=(s:string)=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const urlKey=(url:string)=>{try{const parsed=new URL(url);parsed.hash='';return parsed.href}catch{return url.split('#')[0]}};
const clean=(value:unknown)=>String(value??'').trim();
const ending=(s:string)=>/[.!?…]$/.test(s)?s:s+'.';

/** Electronic-document profile of GOST references, using only supplied factual metadata. */
export function formatBibliography(source:PublicationSource):string{
 const authors=Array.isArray(source.authors)?source.authors.filter(Boolean).join('; '):clean(source.authors);
 let text=ending([authors,source.title.trim()].filter(Boolean).join(' '));
 if(source.journal){
  text=text.replace(/\.$/,'')+' // '+ending(source.journal.trim());
  if(source.year)text+=' — '+ending(String(source.year));
  const volume=source.volume?'Т. '+source.volume:'',issue=source.issue?'№ '+source.issue:'';
  if(volume||issue)text+=' — '+ending([volume,issue].filter(Boolean).join(', '));
  if(source.pages)text+=' — '+ending('С. '+source.pages);
 }else{
  const location=[source.place,source.publisher].filter(Boolean).join(' : ');
  const imprint=[location,source.year].filter(Boolean).join(', ');
  if(imprint)text+=' — '+ending(imprint);
 }
 if(source.release)text+=' — '+ending('Версия: '+source.release);
 if(source.doi)text+=' — '+ending('DOI: '+source.doi.replace(/^https?:\/\/(?:dx\.)?doi\.org\//i,''));
 text+=' — URL: '+source.url;
 if(source.accessed&&/^\d{4}-\d{2}-\d{2}$/.test(source.accessed))text+=' (дата обращения: '+source.accessed.split('-').reverse().join('.')+')';
 return ending(text);
}

/** Number the actual rendered order, then include declared but not inline-cited sources. */
export function buildPublication(material:PublicationMaterial,options:PublicationOptions){
 const bibliography:BibliographyEntry[]=[],byUrl=new Map<string,BibliographyEntry>(),unresolved=new Set<string>();
 const figures:Record<string,FigureInfo>={},images:Record<string,FigureInfo>={};let figureCounter=0,tableCounter=0,imageCounter=0;
 const knownVisuals=new Map(options.visuals.map(v=>[v.id,v])),knownDatasets=new Map(options.datasets.map(d=>[d.id,d])),literature=new Map((options.literature||[]).map(r=>[r.id,r]));
 const declaredVisuals=new Set(material.visualIds);
 const supplied=(s:object)=>Object.fromEntries(Object.entries(s).filter(([,value])=>value!==undefined&&value!==null&&value!==''));
 const resolveSource=(s:PublicationSource):PublicationSource=>{
  const declared=material.sources.find(candidate=>urlKey(candidate.url)===urlKey(s.url));
  const merged={...supplied(declared||{}),...supplied(s)} as PublicationSource;
  const record=merged.referenceId?literature.get(merged.referenceId):undefined;
  return record?{...record,...merged}:merged;
 };
 const register=(source:PublicationSource)=>{
  source=resolveSource(source);const url=urlKey(source.url);let entry=byUrl.get(url);
  if(!entry){entry={id:`source-${bibliography.length+1}`,number:bibliography.length+1,url,title:source.title,text:formatBibliography({...source,url})};bibliography.push(entry);byUrl.set(url,entry)}
  return entry;
 };
 const sourceFor=(ref:string):PublicationSource|undefined=>{
  if(ref.startsWith('source:'))return material.sources[Number(ref.slice(7))-1];
  if(ref.startsWith('data:'))return knownDatasets.get(ref.slice(5));
  const record=literature.get(ref);const url=record?.url||record?.reading_url;if(record&&url)return {...record,url};
 };
 const citation=(ref:string,locator='')=>{
  const source=sourceFor(ref);if(!source){unresolved.add(ref);return `<span class="document-unresolved" data-unresolved-citation="${escapeHtml(ref)}">[источник не найден]</span>`}
  const entry=register(source),label=`[${entry.number}${locator?', '+locator:''}]`;
  return `<a class="document-citation" data-citation-url="${escapeHtml(entry.url)}" href="#${entry.id}" aria-label="Источник ${entry.number}: ${escapeHtml(entry.title)}">${escapeHtml(label)}</a>`;
 };
 const addVisual=(id:string)=>{
  if(figures[id])return figures[id];const visual=knownVisuals.get(id);if(!visual||!declaredVisuals.has(id))return;
  const kind=visual.template==='table'?'table':visual.template==='service-links'?'link':'figure';
  const number=kind==='figure'?++figureCounter:kind==='table'?++tableCounter:undefined;
  const label=kind==='link'?`Интерактивная карта — ${visual.title}`:`${kind==='table'?'Таблица':'Рисунок'} ${number} — ${visual.title}`;
  return figures[id]={id,kind,number,title:visual.title,label,sourceText:'',authored:kind!=='link'};
 };
 const addImage=(image:{href:string;text:string})=>{
  const id=`image-${++imageCounter}`;return images[id]={id,kind:'figure',number:++figureCounter,title:image.text||'Иллюстрация',label:`Рисунок ${figureCounter} — ${image.text||'Иллюстрация'}`,sourceText:'',authored:false};
 };
 const rendererOptions:DocumentOptions={basePath:options.basePath,materialIds:options.materialIds,visualIds:material.visualIds};
 // Prepass resolves forward cross-references without allowing them to change order.
 const outline=renderDocument(material.body,{...rendererOptions,onVisual:addVisual,image:(image)=>{addImage(image);return image.html}});
 const remainingVisualIds=[...new Set(material.visualIds)].filter(id=>!outline.visualIds.includes(id));remainingVisualIds.forEach(addVisual);imageCounter=0;
 const fillVisual=(id:string)=>{
  const info=figures[id];const visual=knownVisuals.get(id);if(!info||!visual)return;
  const data=knownDatasets.get(visual.datasetId);if(!data){unresolved.add('data:'+visual.datasetId);return}
  const entry=register(data);Object.assign(info,{sourceTitle:data.title,sourceNumber:entry.number,sourceUrl:entry.url,sourceId:entry.id,sourceText:`Источник: ${info.authored?'построено автором по данным':'данные'} ${data.title} [${entry.number}]`});
 };
 const document=renderDocument(material.body,{...rendererOptions,citation,onVisual:fillVisual,figureReference:(id)=>{
  const info=figures[id]||images[id];if(!info||info.kind==='link'){unresolved.add('fig:'+id);return `<span class="document-unresolved">[рисунок не найден]</span>`}
  return `<a class="document-figure-reference" data-figure-ref="${escapeHtml(id)}" href="#${figures[id]?'visual-':'illustration-'}${escapeHtml(id)}">${info.kind==='table'?'таблица':'рисунок'} ${info.number}</a>`;
 },image:(image)=>{
  const info=images[`image-${++imageCounter}`],source=material.sources.find(s=>urlKey(s.url)===urlKey(image.href))||{title:info.title,url:image.href};const entry=register(source);
  Object.assign(info,{sourceTitle:source.title,sourceNumber:entry.number,sourceUrl:entry.url,sourceId:entry.id,sourceText:`Источник: ${source.title} [${entry.number}]`});
  return `<span class="document-illustration" role="figure" id="illustration-${info.id}" data-document-image="${info.id}" data-figure-number="${info.number}">${image.html}<span class="document-figure-caption">${escapeHtml(info.label)}</span><span class="document-figure-source">Источник: ${escapeHtml(source.title)} <a class="document-citation" data-citation-url="${escapeHtml(entry.url)}" href="#${entry.id}">[${entry.number}]</a></span></span>`;
 }});
 remainingVisualIds.forEach(fillVisual);material.sources.forEach(register);
 return {document,bibliography,figures,images,remainingVisualIds,unresolvedReferences:[...unresolved]};
}
