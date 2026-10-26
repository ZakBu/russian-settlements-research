/** Render the existing pages once; Pandoc handles Word's document model. */
import {createServer} from 'node:http';
import {createReadStream,existsSync} from 'node:fs';
import {readFile,mkdir,readdir,stat,writeFile,copyFile,mkdtemp,rm} from 'node:fs/promises';
import {resolve,join,extname} from 'node:path';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {chromium} from '@playwright/test';
const web=resolve(import.meta.dirname,'..'),root=resolve(web,'..');
const args=process.argv.slice(2);const value=key=>{const i=args.indexOf(key);return i<0?undefined:args[i+1]};
const site=resolve(value('--site')||join(web,'dist'));
const builtHtml=await readFile(join(site,'index.html'),'utf8').catch(()=> '');
const builtBase=/(?:href|src)="(\/[^"]*?)_astro\//.exec(builtHtml)?.[1];
const base='/' +(builtBase||process.env.PUBLIC_BASE_PATH||'/').replace(/^\/+|\/+$/g,'');
const mount=base==='/'?'':base;
const canonical=(process.env.ATLAS_PUBLIC_URL||'https://zakbu.github.io/russian-settlements-research/').replace(/\/?$/,'/');
const escape=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const all=await Promise.all((await readdir(join(web,'content/materials'))).filter(f=>f.endsWith('.json')).map(async f=>JSON.parse(await readFile(join(web,'content/materials',f),'utf8'))));
const pages=all.filter(m=>m.visibility!=='draft');const published=pages.filter(m=>m.visibility==='published');
const studies=JSON.parse(await readFile(join(web,'content/research.json'),'utf8'));
if(!existsSync(join(site,'knowledge/index.html')))throw Error('Сначала соберите сайт: npm --prefix web run build');
const custom=value('--materials')||value('--material')||value('--research');
const exportDir=join(site,'exports');await mkdir(exportDir,{recursive:true});
let jobs;
if(custom){const ids=value('--materials')?.split(',')||[value('--material')].filter(Boolean);const selected=value('--research')?published.filter(m=>m.researchId===value('--research')).sort((a,b)=>a.publishedAt.localeCompare(b.publishedAt)||a.id.localeCompare(b.id)):ids.map(id=>{const m=pages.find(m=>m.id===id);if(!m)throw Error(`Неизвестный опубликованный материал: ${id}`);return m});if(!selected.length)throw Error('В выборке нет опубликованных материалов');if(!value('--output'))throw Error('Укажите --output file.docx');jobs=[{output:resolve(value('--output')),title:selected.length>1?'Материалы исследования':undefined,ids:selected.map(m=>m.id)}]}
else jobs=[...pages.map(m=>({output:join(exportDir,`${m.id}.docx`),ids:[m.id]})),...studies.map(r=>({output:join(exportDir,`research-${r.id}.docx`),title:`Материалы исследования «${r.title}»`,ids:published.filter(m=>m.researchId===r.id).sort((a,b)=>a.publishedAt.localeCompare(b.publishedAt)||a.id.localeCompare(b.id)).map(m=>m.id)})).filter(j=>j.ids.length)];
const needed=new Set(jobs.flatMap(j=>j.ids));
const scratch=await mkdtemp(join(tmpdir(),'atlas-word-'));
const mime={'.html':'text/html','.js':'application/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2','.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'};
const server=createServer(async(req,res)=>{try{let path=decodeURIComponent(new URL(req.url,'http://localhost').pathname);if(mount&&path.startsWith(mount+'/'))path=path.slice(mount.length);const file=resolve(site,'.'+path+(path.endsWith('/')?'index.html':''));if(!file.startsWith(site+'/')||!(await stat(file)).isFile()){res.writeHead(404).end();return}res.setHeader('Content-Type',mime[extname(file)]||'application/octet-stream');createReadStream(file).pipe(res)}catch{res.writeHead(404).end()}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;
const executable=[process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,'/usr/bin/chromium','/usr/bin/google-chrome',chromium.executablePath()].find(p=>p&&existsSync(p));
let browser;
try{
 browser=await chromium.launch({...(executable?{executablePath:executable}:{}),args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:2});const captures=new Map();
 for(const id of needed){
  const file=join(site,'materials',id,'index.html');if(!existsSync(file))throw Error(`Нет собранной страницы ${id}`);
  await page.goto(`${origin}${mount}/materials/${id}/`,{waitUntil:'networkidle'});await page.evaluate(()=>document.fonts.ready);await page.addStyleTag({content:'.mini-map-controls,.mini-map-status{visibility:hidden!important}*{animation:none!important;transition:none!important}'});
  await page.waitForFunction(()=>[...document.querySelectorAll('.document-body .chart')].every(chart=>chart.querySelector('svg')),undefined,{timeout:30000});
  const visuals=page.locator('.document-body [data-figure-kind="figure"]');const assets={};
  for(let i=0;i<await visuals.count();i++){const figure=visuals.nth(i),key=await figure.getAttribute('data-visual-id');const png=join(scratch,`${id}-${key}.png`);const drawing=figure.locator('[data-figure-graphic]');await drawing.scrollIntoViewIfNeeded();await drawing.screenshot({path:png,animations:'disabled'});assets[key]=png}
  const images=page.locator('.document-body [data-document-image]');for(let i=0;i<await images.count();i++){const figure=images.nth(i),key=await figure.getAttribute('data-document-image');const img=figure.locator('img');await img.scrollIntoViewIfNeeded();await img.evaluate(img=>img.decode());const png=join(scratch,`${id}-${key}.png`);await img.screenshot({path:png});assets[key]=png}
  const data=await page.evaluate(({assets,publicBase,canonical,mount})=>{
   const container=document.createElement('div');const header=document.querySelector('.document-header').cloneNode(true);header.querySelector('h1').id='document-top';header.querySelectorAll('nav,.eyebrow').forEach(e=>e.remove());for(const meta of header.querySelectorAll('.document-meta,.document-context')){const p=document.createElement('p');p.textContent=[...meta.children].map(e=>e.textContent.trim()).filter(t=>!t.includes('мин чтения')).join(' · ');meta.replaceWith(p)}container.append(header);
   const article=document.querySelector('.document-body').cloneNode(true);container.append(article);
   document.querySelectorAll('.document-sources>.document-version,.document-sources>details').forEach(e=>container.append(e.cloneNode(true)));
   container.querySelectorAll('details').forEach(e=>e.open=true);
   for(const figure of container.querySelectorAll('[data-visual-id]')){const id=figure.dataset.visualId,kind=figure.dataset.figureKind;figure.querySelectorAll('.figure-toolbar').forEach(e=>e.remove());if(kind==='figure'){const graphic=figure.querySelector('[data-figure-graphic]');graphic.replaceChildren(Object.assign(document.createElement('img'),{src:assets[id],alt:figure.dataset.figureTitle}));}else if(kind==='link'){figure.dataset.figureKind='link';figure.querySelector('[data-figure-graphic]')?.setAttribute('data-word-interactive-link','true')}}
   for(const figure of container.querySelectorAll('[data-document-image]')){figure.querySelector('img').setAttribute('src',assets[figure.dataset.documentImage]);for(const child of figure.querySelectorAll('.document-figure-caption,.document-figure-source')){const p=document.createElement('p');p.className=child.className;p.innerHTML=child.innerHTML;child.replaceWith(p)}}
   container.querySelectorAll('.heading-anchor,.mini-map-controls,button,script,style,svg').forEach(e=>e.remove());
   for(const a of container.querySelectorAll('a[href]')){const href=a.getAttribute('href');if(href&&!href.startsWith('#')&&!/^[a-z][\w+.-]*:/i.test(href))a.setAttribute('href',href.startsWith('/')?new URL((mount&&href.startsWith(mount+'/')?href.slice(mount.length):href).replace(/^\//,''),canonical).href:new URL(href,publicBase).href)}
   const bibliography=[...document.querySelectorAll('[data-bibliography-url]')].map(e=>({url:e.dataset.bibliographyUrl,text:e.dataset.bibliographyText}));
   return {html:container.innerHTML,bibliography};
  },{assets,publicBase:new URL(`materials/${id}/`,canonical).href,canonical,mount});captures.set(id,data);
 }
 const manifests=[];
 for(const job of jobs){
  const bibliography=[];const byUrl=new Map();let figureCounter=0,tableCounter=0;
  const documents=[];
  for(const id of job.ids){const capture=captures.get(id);const transformed=await page.evaluate(({html,entries,initialFigure,initialTable,knownSources,includedIds})=>{
   const container=document.createElement('div');container.innerHTML=html;const bibliography=[...knownSources];const byUrl=new Map(bibliography.map(e=>[e.url,e]));const known=new Map(entries.map(e=>[e.url,e]));const register=url=>{if(!byUrl.has(url)){const source=known.get(url);if(!source)throw Error(`Нет библиографического источника: ${url}`);const entry={...source,number:bibliography.length+1};bibliography.push(entry);byUrl.set(url,entry)}return byUrl.get(url)};
   let figureCounter=initialFigure,tableCounter=initialTable;const figureNumbers={};
   for(const figure of container.querySelectorAll('[data-figure-kind="figure"],[data-figure-kind="table"],[data-document-image]')){const kind=figure.dataset.figureKind||'figure',number=kind==='table'?++tableCounter:++figureCounter;const key=figure.dataset.visualId||figure.dataset.documentImage;figureNumbers[key]={number,kind};const title=figure.querySelector('.document-figure-caption');if(title)title.textContent=title.textContent.replace(/^(Рисунок|Таблица)\s+\d+/,`$1 ${number}`);figure.dataset.figureNumber=String(number)}
   for(const ref of container.querySelectorAll('[data-figure-ref]')){const figure=figureNumbers[ref.dataset.figureRef];if(figure)ref.textContent=`${figure.kind==='table'?'таблица':'рисунок'} ${figure.number}`}
   for(const cite of container.querySelectorAll('[data-citation-url]')){const entry=register(cite.dataset.citationUrl);cite.textContent=cite.textContent.replace(/^\[\d+/,`[${entry.number}`);cite.setAttribute('href',`#bibliography-${entry.number}`)}
   for(const link of container.querySelectorAll('a.wiki-link[href]')){try{const url=new URL(link.href);const target=/\/materials\/([a-z0-9-]+)\//.exec(url.pathname)?.[1];if(target&&includedIds.includes(target))link.setAttribute('href',`#chapter-${target}-${url.hash?decodeURIComponent(url.hash.slice(1)):'document-top'}`)}catch{}}
   entries.forEach(entry=>register(entry.url));return {html:container.innerHTML,bibliography,figureCounter,tableCounter};
  },{html:capture.html,entries:capture.bibliography,initialFigure:figureCounter,initialTable:tableCounter,knownSources:bibliography,includedIds:job.ids});
   bibliography.splice(0,bibliography.length,...transformed.bibliography);figureCounter=transformed.figureCounter;tableCounter=transformed.tableCounter;
   const m=pages.find(m=>m.id===id);documents.push({id,title:m.title,html:transformed.html,baseUrl:new URL(`materials/${id}/`,canonical).href});
  }
  const bibliographyHtml=`<section id="publication-bibliography"><h1 class="unnumbered">СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ</h1><ol>${bibliography.map(e=>`<li id="bibliography-${e.number}">${escape(e.text.split(e.url)[0])}<a href="${escape(e.url)}">${escape(e.url)}</a>${escape(e.text.slice(e.text.indexOf(e.url)+e.url.length))}</li>`).join('')}</ol></section>`;
  manifests.push({output:job.output,...(job.title?{title:job.title}:{}),documents,bibliographyHtml,toc:true});
 }
 const manifest=join(scratch,'manifest.json');await writeFile(manifest,JSON.stringify({jobs:manifests}));const result=spawnSync(process.env.PYTHON||'python',[join(root,'scripts/export_word.py'),'--input',manifest,...(value('--reference-doc')?['--reference-doc',resolve(value('--reference-doc'))]:[])],{cwd:root,encoding:'utf8',maxBuffer:4*1024*1024});if(result.status!==0)throw Error(result.stderr||result.stdout||'Pandoc export failed');
 if(!custom){const publicExports=join(web,'public/exports');await mkdir(publicExports,{recursive:true});await Promise.all(jobs.map(j=>copyFile(j.output,join(publicExports,j.output.split('/').pop()))));await writeFile(join(exportDir,'manifest.json'),JSON.stringify({profile:'atlas-gost-v1',documents:jobs.map(j=>({file:j.output.split('/').pop(),materials:j.ids}))},null,2));}
 console.log(`Word: ${jobs.length} файлов, ${needed.size} материалов; единая нумерация в каждом документе.`);
}finally{if(browser)await browser.close();await new Promise(r=>server.close(r));await rm(scratch,{recursive:true,force:true})}
