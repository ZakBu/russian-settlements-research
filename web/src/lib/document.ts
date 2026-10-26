import {Marked, Renderer, type Token, type Tokens} from 'marked';
import markedAlert from 'marked-alert';
import markedFootnote from 'marked-footnote';

export type DocumentHeading = {id:string;text:string;depth:number};
export type DocumentBlock = {type:'markdown';html:string}|{type:'visual';id:string};
export type DocumentImage={href:string;src:string;text:string;title?:string|null;html:string};
export type DocumentOptions = {basePath?:string;materialIds?:readonly string[];visualIds?:readonly string[];citation?:(reference:string,locator?:string)=>string;figureReference?:(id:string)=>string;onVisual?:(id:string)=>unknown;image?:(image:DocumentImage)=>string};
export type RenderedDocument = {html:string;headings:DocumentHeading[];blocks:DocumentBlock[];visualIds:string[];links:string[];unresolvedLinks:string[]};

const escapeHtml=(value:string)=>value.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const plainText=(value:string)=>value.replace(/<[^>]*>/g,'').replace(/&(?:amp|lt|gt|quot|#39|#\d+|#x[a-f\d]+);/gi,entity=>{
 const common:Record<string,string>={'&amp;':'&','&lt;':'<','&gt;':'>','&quot;':'"','&#39;':"'"};
 if(common[entity])return common[entity];
 const number=parseInt(entity.slice(entity[2]?.toLowerCase()==='x'?3:2,-1),entity[2]?.toLowerCase()==='x'?16:10);
 return number>0&&number<=0x10ffff?String.fromCodePoint(number):'';
});
const slug=(value:string)=>value.normalize('NFKC').toLocaleLowerCase('ru').replace(/[^\p{L}\p{N}]+/gu,'-').replace(/^-|-$/g,'')||'раздел';
const safeHref=(value:string)=>{
 if(!value||/[\u0000-\u0020\u007f\\]/.test(value)||value.startsWith('//'))return false;
 if(/^https?:\/\//i.test(value)){try{return ['http:','https:'].includes(new URL(value).protocol)}catch{return false}}
 if(/^mailto:[^@\s]+@[^\s]+$/i.test(value))return true;
 return !/^[a-z][a-z\d+.-]*:/i.test(value)&&!value.includes(':');
};

/** Read a small Markdown container, respecting nested details and fenced code examples. */
function detailsContainer(source:string){
 const opening=/^:::details[ \t]+([^\n]+)\n/.exec(source);if(!opening)return;
 let offset=opening[0].length,depth=1,fence='';
 for(const line of source.slice(offset).match(/[^\n]*(?:\n|$)/g)||[]){
  const marker=/^ {0,3}(`{3,}|~{3,})/.exec(line)?.[1];
  if(marker){if(!fence)fence=marker;else if(marker[0]===fence[0]&&marker.length>=fence.length)fence=''}
  if(!fence){if(/^:::(?:details|visual)[ \t]+/.test(line))depth++;else if(/^:::[ \t]*(?:\n|$)/.test(line)&&!--depth)return {raw:source.slice(0,offset+line.length),title:opening[1].trim(),body:source.slice(opening[0].length,offset)}}
  offset+=line.length;
 }
}

/** Build-time Markdown only: no HTML, MDX, executable embeds or arbitrary components. */
export function renderDocument(source:string,options:DocumentOptions={}):RenderedDocument{
 const headings:DocumentHeading[]=[],ids=new Set<string>(),visualIds=new Set<string>(),links=new Set<string>(),unresolvedLinks=new Set<string>();
 const allowedMaterials=options.materialIds?new Set(options.materialIds):undefined,allowedVisuals=new Set(options.visualIds||[]);
 const base=`/${(options.basePath||'/').replace(/^\/+|\/+$/g,'')}`.replace(/\/$/,'');
 const path=(value:string)=>`${base}/${value.replace(/^\//,'')}`;
 let detailsDepth=0;const topVisuals=new Set<Token>();
 const internal=(id:string,label:string,hash='')=>{
  if(allowedMaterials&&!allowedMaterials.has(id)){unresolvedLinks.add(id);return `<span class="document-unresolved" title="Материал недоступен">${label}</span>`}
  links.add(id);return `<a class="wiki-link" href="${escapeHtml(path(`materials/${id}/${hash}`))}">${label}</a>`;
 };
 const renderer=new Renderer();
 renderer.html=()=>'';
 renderer.image=({href,title,text})=>{
  if(!safeHref(href)||!/^https?:\/\//i.test(href)&&!/^\/(?!\/)/.test(href))return escapeHtml(text);
  const src=href.startsWith('/')&&!href.startsWith(`${base}/`)?path(href):href;
  const html=`<img class="document-image" src="${escapeHtml(src)}" alt="${escapeHtml(text)}" loading="lazy" decoding="async"${title?` title="${escapeHtml(title)}"`:''}>`;
  return options.image?options.image({href,src,title,text,html}):html;
 };
 renderer.link=function({href,title,tokens}:Tokens.Link){
  const label=this.parser.parseInline(tokens);if(!safeHref(href))return label;
  const relative=href.replace(new RegExp(`^${base.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}/`),'/');
  const material=/^\/?materials\/([a-z0-9]+(?:-[a-z0-9]+)*)\/?(#[^\s]*)?$/.exec(relative);
  if(material)return internal(material[1],label,material[2]||'');
  const normalized=href.startsWith('/')&&!href.startsWith(`${base}/`)?path(href):href;
  return `<a href="${escapeHtml(normalized)}"${title?` title="${escapeHtml(title)}"`:''}${/^https?:/i.test(href)?' rel="noopener noreferrer"':''}>${label}</a>`;
 };
 renderer.heading=function({tokens,depth}:Tokens.Heading){
  const content=this.parser.parseInline(tokens),text=plainText(content),stem=slug(text);let id=stem,index=2;while(ids.has(id))id=`${stem}-${index++}`;ids.add(id);
  // A material already has its page H1; body titles begin at H2.
  const level=Math.max(2,depth);if(level<=3&&!detailsDepth)headings.push({id,text,depth:level});
  return `<h${level} id="${escapeHtml(id)}" class="document-heading">${content}<a class="heading-anchor" href="#${escapeHtml(id)}" aria-label="Ссылка на раздел: ${escapeHtml(text)}" title="Ссылка на раздел">#</a></h${level}>\n`;
 };
 const markdown=new Marked({gfm:true,renderer,async:false}).use(markedAlert({variants:[
  {type:'note',title:'На заметку',icon:''},{type:'tip',title:'Совет',icon:''},{type:'important',title:'Важно',icon:''},
  {type:'warning',title:'Ограничение',icon:''},{type:'caution',title:'Внимание',icon:''}
 ]}),markedFootnote({prefixId:'doc-footnote-',description:'Примечания',backRefLabel:'Вернуться к упоминанию сноски',refMarkers:true}));
 markdown.use({
  hooks:{processAllTokens(tokens){for(const token of tokens)if(token.type==='documentVisual')topVisuals.add(token);return tokens}},
  extensions:[{
   name:'documentCitation',level:'inline',start:source=>source.indexOf('[@'),
   tokenizer(source){const match=/^\[@((?:source:[1-9]\d*|data:[a-z0-9]+(?:-[a-z0-9]+)*|fig:[a-z0-9]+(?:-[a-z0-9]+)*|[A-Za-z][A-Za-z0-9_:-]*))(?:,[ \t]*([^\]\n]+))?\]/.exec(source);if(match)return {type:'documentCitation',raw:match[0],reference:match[1],locator:match[2]||''}},
   renderer(token){return token.reference.startsWith('fig:')?(options.figureReference?.(token.reference.slice(4))??escapeHtml(token.raw)):(options.citation?.(token.reference,token.locator)??escapeHtml(token.raw))}
  },{
   name:'documentDetails',level:'block',start:source=>source.indexOf(':::details '),
   tokenizer(source){const container=detailsContainer(source);if(container)return {type:'documentDetails',raw:container.raw,title:container.title,tokens:this.lexer.blockTokens(container.body)}},
   childTokens:['tokens'],
   renderer(token){detailsDepth++;let content:string;try{content=this.parser.parse(token.tokens||[])}finally{detailsDepth--}return `<details class="document-details"><summary>${escapeHtml(token.title)}</summary><div class="document-details-content">${content}</div></details>\n`}
  },{
   name:'documentVisual',level:'block',start:source=>source.indexOf(':::visual '),
   tokenizer(source){const match=/^:::visual[ \t]+([a-z0-9]+(?:-[a-z0-9]+)*)[ \t]*\n:::[ \t]*(?:\n|$)/.exec(source);if(match)return {type:'documentVisual',raw:match[0],id:match[1]}},
   renderer(token){
    if(!allowedVisuals.has(token.id))return `<p class="document-unresolved">Визуализация недоступна: ${escapeHtml(token.id)}.</p>\n`;
    if(!topVisuals.has(token))return `<p><a href="${escapeHtml(path(`visuals/${token.id}/`))}">Открыть визуализацию →</a></p>\n`;
    visualIds.add(token.id);options.onVisual?.(token.id);return `<div data-document-visual="${token.id}"></div>\n`;
   }
  },{
   name:'documentWikiLink',level:'inline',start:source=>source.indexOf('[['),
   tokenizer(source){const match=/^\[\[([a-z0-9]+(?:-[a-z0-9]+)*)(#[^\]|\n]+)?(?:\|([^\]\n]+))?\]\]/.exec(source);if(match)return {type:'documentWikiLink',raw:match[0],id:match[1],hash:match[2]||'',label:match[3]||match[1]}},
   renderer(token){return internal(token.id,escapeHtml(token.label),token.hash)}
  }]
 });
 const html=markdown.parse(source) as string,blocks:DocumentBlock[]=[];
 const placeholders=/<div data-document-visual="([a-z0-9-]+)"><\/div>\n?/g;let previous=0;
 for(const match of html.matchAll(placeholders)){const before=html.slice(previous,match.index);if(before.trim())blocks.push({type:'markdown',html:before});blocks.push({type:'visual',id:match[1]});previous=match.index!+match[0].length}
 const tail=html.slice(previous);if(tail.trim())blocks.push({type:'markdown',html:tail});
 return {html,headings,blocks,visualIds:[...visualIds],links:[...links],unresolvedLinks:[...unresolvedLinks]};
}
