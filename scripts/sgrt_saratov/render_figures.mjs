/** Export scientific figures through the existing atlas/editor.
 * Local frozen GeoJSON is served to the existing editor with route interception.
 * The actual producer's renderer and legend helpers are applied to its map.
 * This is source-backed figure rendering, NEVER verification of public datasets.
 * Browser/GPU/basemap pixels are not claimed to be numerically reproducible.
 */
import {readFileSync,writeFileSync,mkdirSync,statSync} from 'node:fs';
import {resolve,dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {execFileSync,spawnSync} from 'node:child_process';

const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const req=createRequire(import.meta.url);
const args={};
for(let i=2;i<process.argv.length;i++){
 const key=process.argv[i];
 if(key==='--require-clean-producer'){args[key]=true;continue;}
 if(!key.startsWith('--')||!process.argv[i+1])throw Error('Expected --name value');
 args[key]=process.argv[++i];
}
if(!args['--results']||!args['--source-commit'])throw Error('--results and --source-commit required');
const results=resolve(args['--results']),output=resolve(args['--output']||join(results,'figures'));
const base=(args['--base-url']||'https://zakbu.github.io/russian-settlements-research/').replace(/\/?$/,'/');
const {chromium}=req(process.env.SGRT_FIGURE_PLAYWRIGHT_MODULE||'playwright');
const ts=req(process.env.SGRT_FIGURE_TYPESCRIPT_MODULE||'typescript');
const playwrightVersion=req((process.env.SGRT_FIGURE_PLAYWRIGHT_MODULE||'playwright')+'/package.json').version;
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const readJSON=path=>JSON.parse(readFileSync(path,'utf8'));
const write=(path,value)=>writeFileSync(path,JSON.stringify(value,null,2)+'\n');
const renderer=join(repo,'web/src/components/custom-map-layers.ts');
const rendererBytes=readFileSync(renderer);const rendererSHA=sha(rendererBytes);
const moduleJS=ts.transpileModule(rendererBytes.toString('utf8'),{fileName:renderer,
 compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext},reportDiagnostics:true});
if((moduleJS.diagnostics||[]).some(d=>d.category===ts.DiagnosticCategory.Error))throw Error('Producer renderer does not compile');
const head=execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8'}).trim();
const tracked=spawnSync('git',['ls-files','--error-unmatch','scripts/sgrt_saratov/render_figures.mjs'],{cwd:repo,stdio:'ignore'}).status===0;
const clean=head===args['--source-commit']&&tracked&&spawnSync('git',['diff','--quiet','HEAD','--',
 'scripts/sgrt_saratov/render_figures.mjs','web/src/components/custom-map-layers.ts'],{cwd:repo}).status===0;
if(args['--require-clean-producer']&&!clean)throw Error('Committed exact scientific producer renderer required');
const schoolLabels={'0':'Питерка','1':'Мироновка','2':'Агафоновка','3':'Новотулка','4':'Другие известные школьные площадки'};
const medicalLabels=readJSON(join(results,'medical_competition/summary.json')).centre_display_class_labels;
const specs=[
 {id:'school-baseline',asset:'saratov-school-baseline.png',file:'school_competition/baseline_zones.geojson',title:'Школы: исходные сведения',labels:schoolLabels,period:'Дорожная сеть 2021; сведения разных лет',description:'Ближайшие известные школьные площадки. Обобщённые контуры; это не наблюдённые поездки учеников.'},
 {id:'school-enriched',asset:'saratov-school-enriched.png',file:'school_competition/documented_campus_enriched_zones.geojson',title:'Школы: уточнённые филиалы',labels:schoolLabels,period:'Дорожная сеть 2021; школьные документы 2025',description:'Добавлены документированные места филиалов. Для площадок без координат здания используется точка населённого пункта.'},
 {id:'medical-basic',asset:'saratov-medical-basic.png',file:'medical_competition/medical_basic_zones.geojson',title:'Базовая первичная помощь',labels:medicalLabels,period:'Дорожная сеть 2021; медицинские источники разных лет',description:'Отдельная потребность: ближайшая известная площадка первичной помощи. Это не наблюдённые обращения пациентов.'},
 {id:'medical-physician',asset:'saratov-medical-physician.png',file:'medical_competition/medical_physician_zones.geojson',title:'Врачебная первичная помощь',labels:medicalLabels,period:'Дорожная сеть 2021; медицинские источники разных лет',description:'Отдельная потребность: ближайшая известная площадка врачебной помощи. Местная базовая помощь сохраняется.'}
];
mkdirSync(output,{recursive:true});
const view={lat:50.7,lng:47.5,zoom:8.2,viewport:{width:1440,height:1000},deviceScaleFactor:1};
const proof={schema:'sgrt.saratov.existing_editor_figure_export.v1',
 local_source_rendering:true,public_dataset_qa:false,route_interception:true,pixel_numeric_reproducibility_claimed:false,
 editor_origin_url:base,source_commit:args['--source-commit'],actual_head:head,producer_renderer_committed_clean:clean,
 renderer_source:'web/src/components/custom-map-layers.ts',renderer_source_sha256:rendererSHA,
 exporter_source_sha256:sha(readFileSync(fileURLToPath(import.meta.url))),
 playwright_version:playwrightVersion,typescript_version:ts.version,node_version:process.version,view,figures:[]};
const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']});
proof.browser_version=browser.version();
try{
 for(const spec of specs){
  const file=join(results,spec.file),bytes=readFileSync(file),raw=JSON.parse(bytes.toString());
  if(raw.type!=='FeatureCollection'||!raw.features.length)throw Error('A nonempty source feature collection is required');
  const payload={type:'FeatureCollection',features:raw.features.map((f,i)=>{
   if(!f.geometry?.coordinates?.length)throw Error('Empty source geometry');
   const value=f.properties.class_index;if(!Number.isFinite(value)||!spec.labels[String(value)])throw Error('Unlabelled source category');
   return {...f,id:String(f.properties.id??i),properties:{id:String(f.properties.id??i),name:f.properties.name,value}};
  })};
  const id='saratov-figure-'+spec.id;
  const meta={id,researchId:'sgrt',title:spec.title,description:spec.description,geometry:'polygon',
   path:'custom-layers/'+id+'.geojson',palette:'categorical',valueLabels:spec.labels,unit:'направления обслуживания',
   period:spec.period,evidence:'model',source:{title:'Расчёт и закреплённые источники исследования',
   url:'https://github.com/ZakBu/russian-settlements-research/tree/'+args['--source-commit']}};
  const context=await browser.newContext({viewport:view.viewport,deviceScaleFactor:view.deviceScaleFactor,ignoreHTTPSErrors:true});
  await context.route('**/data/layers.json*',r=>r.fulfill({contentType:'application/json',body:JSON.stringify([meta])}));
  await context.route('**/data/custom-layers/'+id+'.geojson*',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(payload)}));
  const page=await context.newPage();const pageErrors=[];
  page.on('pageerror',error=>pageErrors.push(error.message));
  const url=base+`map/?research=sgrt&layers=${id}&period=2021&lat=${view.lat}&lng=${view.lng}&zoom=${view.zoom}`;
  const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:90000});
  if(!response?.ok())throw Error('Existing atlas/editor did not load');
  await page.waitForFunction(id=>{const e=document.querySelector('input[data-layer-id="'+id+'"]');
   return e&&e.checked&&e.closest('label').textContent.includes('объект');},id,{timeout:90000});
  if(await page.getByRole('button',{name:'Закрыть слои'}).isVisible())await page.getByRole('button',{name:'Закрыть слои'}).click();
  await page.waitForTimeout(8000);
  const check=await page.evaluate(async({javascript,meta,payload})=>{
   const module=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(javascript))));
   let map;
   for(const element of document.querySelectorAll('*')){
    for(const key of Object.keys(element).filter(k=>k.startsWith('__reactFiber$'))){
     let fiber=element[key];const visited=new Set();
     while(fiber&&!visited.has(fiber)){visited.add(fiber);let hook=fiber.memoizedState,n=0;
      while(hook&&n++<100){const value=hook.memoizedState;
       if(value?.current&&typeof value.current.getStyle==='function'&&value.current.getLayer('research-'+meta.id+'-fill')){map=value.current;break;}
       hook=hook.next;
      }if(map)break;fiber=fiber.return;
     }if(map)break;
    }if(map)break;
   }
   if(!map)throw Error('Loaded existing editor map reference not found');
   module.renderResearchLayer(map,meta,payload,true,false);
   const entries=module.researchLegendEntries(meta,payload,false);
   if(!entries.length||entries.some(r=>!r.label.trim()||/^\d+(?:\s*[–-]\s*\d+)?$/.test(r.label)))throw Error('Readable categorical legend required');
   const legend=document.querySelector('.map-custom-legend>div');
   if(!legend)throw Error('Existing editor legend not found');
   for(const span of legend.querySelectorAll(':scope>span'))span.remove();
   const anchor=legend.querySelector('small');
   for(const item of entries){const span=document.createElement('span'),swatch=document.createElement('i');
    swatch.style.background=item.color;span.append(swatch,document.createTextNode(item.label));legend.insertBefore(span,anchor);}
   await new Promise(resolve=>{map.once('idle',resolve);setTimeout(resolve,4000);});
   const rendered=map.queryRenderedFeatures({layers:['research-'+meta.id+'-fill']});
   const opacity=map.getPaintProperty('research-'+meta.id+'-fill','fill-opacity');
   const outline=map.getPaintProperty('research-'+meta.id+'-outline','line-width');
   if(!rendered.length||opacity!==.6||outline!==1||!map.isStyleLoaded())throw Error('Map geometry/style QC failed');
   return {actual_producer_renderer_applied:true,geometry_source_feature_count:payload.features.length,
    rendered_feature_instances:rendered.length,plain_legend_labels:entries.map(r=>r.label),
    full_class_labels:meta.valueLabels,fill_opacity:opacity,outline_width:outline,map_style_loaded:map.isStyleLoaded(),
    source_data_is_local_frozen_model_output:true,public_data_delivery_verified:false};
  },{javascript:moduleJS.outputText,meta,payload});
  await page.waitForTimeout(1000);await page.screenshot({path:join(output,spec.asset),animations:'disabled'});
  if(pageErrors.length)throw Error('Existing editor page errors: '+pageErrors.join('; '));
  if(sha(readFileSync(file))!==sha(bytes)||sha(readFileSync(renderer))!==rendererSHA)throw Error('Frozen figure input changed while rendering');
  if(statSync(join(output,spec.asset)).size<10_000)throw Error('Figure file unexpectedly small');
  proof.figures.push({id:spec.id,asset:spec.asset,source_file:spec.file,source_sha256:sha(bytes),
   editor_url:url,bytes:statSync(join(output,spec.asset)).size,sha256:sha(readFileSync(join(output,spec.asset))),...check});
  await context.close();console.log(JSON.stringify({figure:spec.asset,source_features:payload.features.length,status:'rendered_local_source_not_public_qa'}));
 }
}finally{await browser.close();write(join(output,'render_proof.json'),proof);}
if(proof.figures.length!==4)throw Error('Exactly four scientific map figures required');
console.log(JSON.stringify({figures:proof.figures.length,proof:join(output,'render_proof.json'),public_qa:false}));
