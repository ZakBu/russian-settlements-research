'use strict';
// Real public QA only. No route interception, injected data or local substitutions.
const fs=require('fs'); const path=require('path'); const crypto=require('crypto');
// Set PLAYWRIGHT_BROWSERS_PATH in the caller when using a shared browser cache.
// SGRT_BROWSER_MODULE may point to an existing Playwright installation.
const args=process.argv.slice(2);
const take=k=>args.includes(k)?args[args.indexOf(k)+1]:null;
if(args.includes('--help')){
 console.log('Usage: node scripts/sgrt_saratov/verify_public_atlas.cjs --go --producer <40hex> --output <directory> [--base-url <URL>] [--articles <comma-separated IDs>] [--skip-maps]\nDefault: four articles and 13 map layers at two viewports. Targeted runs report their exact limited scope.\nRequires playwright (or SGRT_BROWSER_MODULE) and its Chromium installation. No data interception or substitution.');
 process.exit(0);
}
if(!args.includes('--go')){console.error('Not run: explicit --go after the selected site deployment is required.');process.exit(2);}
const producer=take('--producer');if(!/^[a-f0-9]{40}$/.test(producer||'')){console.error('Expected real 40-character producer commit with --producer.');process.exit(2);}
const outputArg=take('--output');if(!outputArg||outputArg.startsWith('--')){console.error('Expected --output <directory> for screenshots and verification JSON.');process.exit(2);}
const out=path.resolve(outputArg);
let chromium;try{({chromium}=require(process.env.SGRT_BROWSER_MODULE||'playwright'));}catch(error){console.error('Playwright is unavailable. Install playwright or set SGRT_BROWSER_MODULE to an existing installation. '+error.message);process.exit(2);}
const repo=path.resolve(__dirname,'../..');
const registered=path.join(repo,'web/content');
const baseArg=take('--base-url')||'https://zakbu.github.io/russian-settlements-research/';
const base=new URL(baseArg.endsWith('/')?baseArg:baseArg+'/').href;
// APIRequestContext does not automatically inherit the environment proxy.
// Use the same configured network route for browser and API requests; never log credentials.
function environmentProxy(){const value=process.env.HTTPS_PROXY||process.env.https_proxy||process.env.HTTP_PROXY||process.env.http_proxy;if(!value)return undefined;const url=new URL(value),proxy={server:url.protocol+'//'+url.host};if(url.username)proxy.username=decodeURIComponent(url.username);if(url.password)proxy.password=decodeURIComponent(url.password);return proxy;}
const read=f=>JSON.parse(fs.readFileSync(f,'utf8'));
const scopeIds=[
 'saratov-basic-centres',
 'saratov-iso-saratov','saratov-iso-engels','saratov-iso-balakovo',
 'saratov-iso-balashov','saratov-iso-novouzensk','saratov-iso-piterka',
 'saratov-school-baseline-zones','saratov-school-baseline-time',
 'saratov-school-enriched-zones','saratov-school-enriched-time',
 'saratov-medical-basic-zones','saratov-medical-physician-zones'
];
const configs=scopeIds.map(id=>read(path.join(registered,'layers',id+'.json')));
const datasets=read(path.join(registered,'datasets.json'));
const main=read(path.join(registered,'materials/saratov-functional-systems.json'));
const expectedVisuals=main.visualIds;
const defaultArticles=['saratov-functional-systems','saratov-functional-method','saratov-isochrones','literature-bibliography'];
const articleArg=take('--articles');
check(!args.includes('--articles')||!!articleArg,'Expected --articles <comma-separated IDs>');
const articleIds=articleArg?articleArg.split(',').map(x=>x.trim()).filter(Boolean):defaultArticles;
check(articleIds.length>0&&new Set(articleIds).size===articleIds.length&&articleIds.every(id=>defaultArticles.includes(id)),'--articles must list unique IDs from the four supported publication pages');
const skipMaps=args.includes('--skip-maps');
const scopedMaps=skipMaps?[]:configs;
const viewports=[{width:1366,height:900},{width:390,height:844}];
const proof={schema:'sgrt.real_public_browser_qa.v1',started_utc:new Date().toISOString(),base,expected_producer:producer,registered_metadata_root:registered,scoped_layer_ids:scopedMaps.map(x=>x.id),scope:{article_ids:articleIds,map_layer_ids:scopedMaps.map(x=>x.id),viewports,full_default_scope:!articleArg&&!skipMaps},route_interception:false,local_data_substitution:false,articles:[],maps:[],failures:[],requests_failed:[]};
const errors=[];let browser;
function check(condition,message){if(!condition)throw Error(message);}
function flush(){fs.writeFileSync(out+'/browser-verification.json',JSON.stringify(proof,null,2)+'\n');}
function sha(b){return crypto.createHash('sha256').update(b).digest('hex');}
function canonical(value){if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';return JSON.stringify(value);}
function literalNumber(value){if(value===null||value===undefined||(typeof value==='string'&&!value.trim()))return null;const n=Number(value);check(Number.isFinite(n),'Nonfinite source value');return n;}
function compareNormalizedGeoJSON(meta,raw,actual){
 check(meta.adapter==='geojson','Literal QA adapter only supports declared GeoJSON layers');
 check(raw.type==='FeatureCollection'&&Array.isArray(raw.features),'Invalid original source FeatureCollection');
 check(raw.features.length===actual.features.length,'Published and original feature counts differ');
 const originals=new Map();for(const f of raw.features){const row=f.properties||{},id=String(row[meta.fields.id]).trim();check(id&&!originals.has(id),'Original feature ID missing or duplicated');originals.set(id,f);}
 const seen=new Set();let settlementIdsCompared=0;
 for(const f of actual.features){const id=String(f.id);check(!seen.has(id),'Duplicated published feature ID');seen.add(id);const original=originals.get(id);check(original,'Published feature not in original source: '+id);const row=original.properties||{};
  check(f.properties.id===id,'Published properties.id differs from feature.id: '+id);
  check(f.properties.name===String(row[meta.fields.name]),'Published name differs: '+id);
  const expected=meta.fields.value?literalNumber(row[meta.fields.value]):null;check(f.properties.value===expected,'Published value differs: '+id);
  check(canonical(f.geometry)===canonical(original.geometry),'Published geometry differs: '+id);
  if(Object.hasOwn(f.properties,'settlementId')){const sourceId=row.settlementId??(meta.fields.settlementKey?row[meta.fields.settlementKey]:undefined);check(sourceId!==undefined&&String(f.properties.settlementId)===String(sourceId),'Published settlement identity differs: '+id);settlementIdsCompared++;}
 }
 return {all_features_compared:actual.features.length,fields:['id','name','value','geometry'],settlement_ids_compared_when_present:settlementIdsCompared,source_extra_properties_discarded_as_declared_geojson_adapter:true};
}
async function fullScroll(page){await page.evaluate(()=>scrollTo(0,0));let last=-1;for(let n=0;n<120;n++){const y=await page.evaluate(()=>{const end=document.documentElement.scrollHeight-innerHeight;scrollBy(0,Math.floor(innerHeight*.8));return {y:scrollY,end};});await page.waitForTimeout(100);if(y.y>=y.end-2||y.y===last)break;last=y.y;}await page.evaluate(()=>scrollTo(0,0));}
async function shot(page,name,fullPage=false){await page.screenshot({path:path.join(out,name+'.png'),fullPage,timeout:45000});}
async function article(context,id,width){
 const page=await context.newPage();const pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));
 const entry={id,width,url:base+'materials/'+id+'/',page_errors:pageErrors};proof.articles.push(entry);flush();
 try{
  const response=await page.goto(entry.url,{waitUntil:'domcontentloaded',timeout:90000});entry.status=response.status();check(entry.status===200,'Article HTTP '+entry.status);
  const body=await page.locator('article.article-body').innerText();check(body.length>200,'Empty article');entry.body_characters=body.length;
  if(id.startsWith('saratov-')&&id!=='saratov-isochrones'){
   const sourceHrefs=await page.locator('.document-version a').evaluateAll(es=>es.map(e=>e.href));check(sourceHrefs.some(h=>h.endsWith('/commit/'+producer)),'Wrong or stale producer in article');
  }
  check(!/PENDING_ACTUAL|PENDING_FINAL|PENDING_PUBLISHED/.test(body),'Unresolved publication placeholder');
  if(id==='saratov-functional-systems'){
   entry.visual_ids=await page.locator('figure[data-visual-id]').evaluateAll(es=>es.map(e=>e.dataset.visualId));
   check(JSON.stringify([...entry.visual_ids].sort())===JSON.stringify([...expectedVisuals].sort()),'Visual declarations differ from prepared final article');
   entry.image_results=[];
   for(const name of ['saratov-school-baseline','saratov-school-enriched','saratov-medical-basic','saratov-medical-physician']){
    const img=page.locator(`article img[src*="${name}.png"]`);check(await img.count()===1,'Missing expected illustration '+name);await img.scrollIntoViewIfNeeded();
    await img.evaluate(img=>img.decode());const data=await img.evaluate(e=>({url:e.currentSrc,width:e.naturalWidth,height:e.naturalHeight,complete:e.complete,alt:e.alt}));check(data.complete&&data.width>0&&data.height>0,'Broken real public image '+name);entry.image_results.push(data);
   }
   for(const visualId of expectedVisuals){
    const figure=page.locator(`figure[data-visual-id="${visualId}"]`);await figure.scrollIntoViewIfNeeded();check((await figure.innerText()).trim().length>30,'Empty visual '+visualId);
    const links=await figure.locator('a').evaluateAll(es=>es.map(e=>({href:e.href,text:e.textContent.trim()})));entry.visual_links??={};entry.visual_links[visualId]=links;
    if(visualId.endsWith('-map'))check(links.some(l=>l.href.includes('/map/?')&&l.href.includes('layers=')),'Missing map deep link '+visualId);
    else check(await figure.locator('canvas,svg').count()>0,'Chart has no rendered canvas/SVG '+visualId);
   }
  }
  await fullScroll(page);
  const toc=width<600?page.locator('.document-mobile-toc'):page.locator('nav[aria-label="На этой странице"]');
  if(width<600){await page.locator('.document-mobile-toc summary').click();check(await page.locator('.document-mobile-toc').getAttribute('open')!==null,'Mobile TOC did not open');}
  const link=toc.locator('a[href^="#"]').first();const target=await link.getAttribute('href');await link.click();await page.waitForTimeout(200);check(decodeURIComponent(new URL(page.url()).hash)===decodeURIComponent(target),'TOC navigation did not change anchor');check(await page.evaluate(id=>!!document.getElementById(decodeURIComponent(id.slice(1))),target),'TOC target absent');entry.toc_anchor=target;
  if(width<600)await page.locator('.document-mobile-toc summary').click();
  const details=page.locator('.document-sources details').first();if(await details.count()){await details.locator('summary').click();check(await details.getAttribute('open')!==null,'Data details did not open');entry.source_details_opened=true;await details.locator('summary').click();}
  entry.overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);check(!entry.overflow,'Article horizontal viewport overflow');
  check(pageErrors.length===0,'Article JavaScript error: '+pageErrors.join('; '));
  await page.evaluate(()=>scrollTo(0,0));await shot(page,id+'-'+width,true);entry.ok=true;
 }catch(e){entry.ok=false;entry.error=e.message;proof.failures.push({kind:'article',id,width,error:e.message});await shot(page,id+'-'+width+'-failure',true).catch(()=>{});}finally{flush();await page.close();}
}
function mapPosition(id){
 const vis=main.visualIds.map(v=>read(registered+'/visuals/'+v+'.json')).find(v=>v.mapState?.layers?.includes(id));if(vis)return vis.mapState;
 const iso={saratov:[51.53,46.035],engels:[51.501667,46.122222],balakovo:[52.03898,47.78392],balashov:[51.55,43.166667],novouzensk:[50.45,48.15],piterka:[50.6771317,47.4444037]};
 if(id.startsWith('saratov-iso-')){const a=iso[id.slice(12)];return{lat:a[0],lng:a[1],zoom:8.5};}return{lat:50.7,lng:47.5,zoom:8.2};
}
function world(lon,lat,z){const s=512*Math.pow(2,z),sin=Math.sin(lat*Math.PI/180);return [(lon+180)/360*s,(.5-Math.log((1+sin)/(1-sin))/(4*Math.PI))*s];}
function points(geometry){if(!geometry)return[];if(geometry.type==='Point')return[geometry.coordinates];if(geometry.type==='MultiPoint'||geometry.type==='LineString')return geometry.coordinates;if(geometry.type==='Polygon'||geometry.type==='MultiLineString')return geometry.coordinates.flat();if(geometry.type==='MultiPolygon')return geometry.coordinates.flat(2);return[];}
async function tryPopup(page,data,position){
 const rect=await page.locator('.maplibregl-canvas').boundingBox();if(!rect)return null;const center=world(position.lng,position.lat,position.zoom);
 const candidates=[];for(const f of data.features){const ps=points(f.geometry);if(!ps.length)continue;if(f.geometry.type==='Point')candidates.push(ps[0]);else{const xs=ps.map(p=>p[0]),ys=ps.map(p=>p[1]);candidates.push([(Math.min(...xs)+Math.max(...xs))/2,(Math.min(...ys)+Math.max(...ys))/2]);}}
 for(const p of candidates.slice(0,80)){const q=world(p[0],p[1],position.zoom),x=rect.x+rect.width/2+q[0]-center[0],y=rect.y+rect.height/2+q[1]-center[1];if(x<rect.x+25||x>rect.x+rect.width-25||y<rect.y+80||y>rect.y+rect.height-130)continue;await page.mouse.click(x,y);await page.waitForTimeout(120);const pop=page.locator('.map-evidence-popup');if(await pop.isVisible())return{text:await pop.innerText(),links:await pop.locator('a').evaluateAll(es=>es.map(e=>({text:e.textContent.trim(),url:e.href}))),clicked_geographic_position:p};}
 return null;
}
async function map(context,meta,width){
 const page=await context.newPage();const pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));const dataset=datasets.find(d=>d.id===meta.datasetId);check(dataset,'Dataset missing '+meta.id);const position=mapPosition(meta.id);const query=new URLSearchParams({research:'sgrt',layers:meta.id+',regions',period:'2021',lat:position.lat,lng:position.lng,zoom:position.zoom});const entry={id:meta.id,width,url:base+'map/?'+query,source_url:dataset.url,page_errors:pageErrors};proof.maps.push(entry);flush();
 let data=null;let sourceResponse=null;
 const exportedUrl=base+'data/custom-layers/'+meta.id+'.geojson';
 const capture=async response=>{let request=response.request(),matched=false;for(let n=0;n<12&&request;n++,request=request.redirectedFrom()){if(request.url().split('?')[0]===exportedUrl.split('?')[0])matched=true;}if(matched&&response.status()===200){try{const b=await response.body();data=JSON.parse(b.toString());sourceResponse={url:exportedUrl,resolved_origin:new URL(response.url()).origin,status:response.status(),sha256:sha(b),bytes:b.length,content_type:response.headers()['content-type']};}catch(e){entry.source_read_error=e.message;}}};
 page.on('response',capture);
 try{
  const response=await page.goto(entry.url,{waitUntil:'domcontentloaded',timeout:90000});entry.status=response.status();check(entry.status===200,'Map HTTP '+entry.status);
  const input=page.locator(`input[data-layer-id="${meta.id}"]`);await input.waitFor({state:'attached',timeout:90000});check(await input.isChecked(),'Deep link did not activate layer');
  await page.waitForFunction(id=>{const e=document.querySelector(`input[data-layer-id="${id}"]`);return e?.closest('label')?.textContent.includes('объект')&&!e.closest('label').textContent.includes('загрузка…')},meta.id,{timeout:120000});
  check(await page.locator('.map-custom-error').count()===0,'Research layer loading error');
  for(let n=0;n<100&&!data;n++)await page.waitForTimeout(100);check(data?.type==='FeatureCollection','Actual public custom-layer UI GeoJSON response not captured');check(sourceResponse.status===200,'Layer data HTTP '+sourceResponse.status);entry.browser_source=sourceResponse;entry.feature_count=data.features.length;
  const registryResponse=await context.request.get(base+'data/layers.json',{timeout:90000});check(registryResponse.status()===200,'Public layer registry HTTP '+registryResponse.status());const registry=await registryResponse.json(),published=registry.find(x=>x.id===meta.id);check(published,'Layer absent from deployed public registry');check(published.path==='custom-layers/'+meta.id+'.geojson','Wrong public exported layer path');check(published.source.url===dataset.url&&published.source.sha256===dataset.sha256&&published.source.sourceCommit===dataset.sourceCommit,'Deployed registry source metadata differs from registered immutable dataset');entry.public_registry_source=published.source;
  const originalResponse=await context.request.get(dataset.url,{timeout:90000});check(originalResponse.status()===200,'Original published source HTTP '+originalResponse.status());const originalBytes=await originalResponse.body();check(sha(originalBytes)===dataset.sha256,'Original published Release bytes differ from registered SHA');entry.original_source={url:dataset.url,status:originalResponse.status(),bytes:originalBytes.length,sha256:sha(originalBytes)};entry.normalized_source_comparison=compareNormalizedGeoJSON(meta,JSON.parse(originalBytes.toString()),data);
  const legend=page.locator('.map-custom-legend');await legend.waitFor({state:'visible',timeout:30000});entry.legend=await legend.innerText();entry.layer_label=await input.locator('..').innerText();check(entry.legend.includes(meta.title),'Legend title mismatch');check(entry.legend.includes('Модельная оценка'),'Legend misses model evidence');check(entry.legend.includes(meta.description),'Legend misses scope/limitations');check(await legend.locator('a').getAttribute('href')===dataset.url,'Legend source link mismatch');
  const observed=[...new Set(data.features.map(f=>String(f.properties.value)).filter(v=>v!=='null'&&v!=='undefined'))];
  if(meta.valueLabels){for(const value of observed)check(entry.legend.includes(meta.valueLabels[value]),'Missing named legend category '+value);entry.named_categories=observed.map(v=>meta.valueLabels[v]);}
  entry.swatches=await legend.locator('span').evaluateAll(es=>es.map(e=>({label:e.textContent.trim(),color:e.querySelector('i')?getComputedStyle(e.querySelector('i')).backgroundColor:null})));check(entry.swatches.every(x=>x.color&&x.color!=='rgba(0, 0, 0, 0)'),'Transparent/missing legend swatch');
  const rgb=entry.swatches.map(s=>(s.color.match(/[\d.]+/g)||[]).slice(0,3).map(Number));entry.minimum_swatch_rgb_distance=rgb.length>1?Math.min(...rgb.flatMap((a,i)=>rgb.slice(i+1).map(b=>Math.hypot(...a.map((x,k)=>x-b[k]))))):null;if(meta.valueLabels&&rgb.length>1)check(entry.minimum_swatch_rgb_distance>25,'Named legend colours insufficiently distinct');
  const close=page.getByRole('button',{name:'Закрыть слои',exact:true});if(await close.isVisible())await close.click();await page.waitForTimeout(1800);
  entry.popup=await tryPopup(page,data,position);if(!entry.popup&&meta.geometry==='point')throw Error('Cannot open centre popup by actual geographic click');
  if(entry.popup){check(entry.popup.links.some(x=>x.url===dataset.url),'Popup lacks pinned source URL');check(entry.popup.text.includes('Модельная оценка'),'Popup lacks model evidence');}
  check(pageErrors.length===0,'Map JavaScript error: '+pageErrors.join('; '));await shot(page,meta.id+'-'+width);entry.ok=true;
  if(meta.id==='saratov-school-enriched-zones'&&width===1366){await page.locator('#theme-toggle').click();await page.waitForTimeout(400);entry.dark_legend=await legend.innerText();check(entry.named_categories.every(x=>entry.dark_legend.includes(x)),'Named categories disappear in dark theme');await shot(page,meta.id+'-'+width+'-dark');}
 }catch(e){entry.ok=false;entry.error=e.message;proof.failures.push({kind:'map',id:meta.id,width,error:e.message});await shot(page,meta.id+'-'+width+'-failure').catch(()=>{});}finally{page.removeListener('response',capture);flush();await page.close();}
}
(async()=>{fs.mkdirSync(out,{recursive:true});browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']});try{
 for(const viewport of viewports){
  const context=await browser.newContext({viewport,ignoreHTTPSErrors:true,proxy:environmentProxy()});context.on('requestfailed',request=>proof.requests_failed.push({url:new URL(request.url()).origin+new URL(request.url()).pathname,error:request.failure()?.errorText,width:viewport.width}));
  for(const id of articleIds)await article(context,id,viewport.width);
  for(const meta of scopedMaps)await map(context,meta,viewport.width);
  await context.close();
 }
}finally{proof.finished_utc=new Date().toISOString();proof.ok=proof.failures.length===0;flush();await browser.close();}
console.log(JSON.stringify({ok:proof.ok,articles:proof.articles.length,maps:proof.maps.length,failures:proof.failures},null,2));if(!proof.ok)process.exitCode=1;})().catch(e=>{proof.fatal_error=e.stack;flush();console.error(e);process.exitCode=1;});
