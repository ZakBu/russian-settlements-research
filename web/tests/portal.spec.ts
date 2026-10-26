import {readFileSync} from 'node:fs';
import {test,expect} from '@playwright/test';

test('atlas search, no-results and reset preserve a usable catalogue',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('atlas/');await expect(page.getByRole('heading',{name:'Материалы',exact:true})).toBeVisible();await expect(page).toHaveURL(/materials\/\?view=cards/);
 const cards=page.locator('[data-material-card]:visible');const total=await cards.count();expect(total).toBeGreaterThan(5);
 await page.getByRole('searchbox',{name:'Поиск материалов'}).fill('197 центров');await expect.poll(()=>cards.count()).toBeGreaterThan(0);
 await page.getByRole('searchbox',{name:'Поиск материалов'}).fill('несуществующий-материал-xyz');await expect(cards).toHaveCount(0);
 await page.getByRole('button',{name:'Сбросить поиск и фильтры'}).click();await expect(cards).toHaveCount(total);
 const lead=page.locator('[data-material-id="population-base"][data-material-card]');expect((await lead.boundingBox())!.height).toBeLessThan(850);
 await lead.scrollIntoViewIfNeeded();await expect(lead.locator('.cartographic-preview')).toBeVisible();await expect.poll(()=>lead.locator('.map-image-light').evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0)).toBe(true);expect(errors).toEqual([]);
});

test('research selection survives navigation and dark theme survives reload',async({page})=>{
 await page.goto('materials/');await page.locator('[data-catalog-research="ecommerce"]').click();await expect(page).toHaveURL(/materials\/\?research=ecommerce/);
 await expect(page.locator('[data-material-list]:visible')).toHaveCount(2);
 await expect(page.locator('[data-catalog-research="ecommerce"]')).toHaveAttribute('aria-current','page');
 await page.locator('[data-material-list]:visible h2 a').first().click();await expect(page.getByRole('heading',{level:1})).toBeVisible();await page.goBack();
 await expect(page).toHaveURL(/materials\/\?research=ecommerce/);await expect(page.locator('[data-material-list]:visible')).toHaveCount(2);
 await page.locator('#theme-toggle').click();await expect(page.locator('html')).toHaveAttribute('data-theme','dark');await page.reload();await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
});

test('morning updates are meaningful and can be marked read',async({page})=>{
 await page.goto('');const count=page.locator('[data-new-count]');await expect(count).toBeVisible();expect(Number(await count.textContent())).toBeGreaterThan(0);
 await page.locator('[data-mark-read]').click();await expect(count).toHaveText('0');
 await page.locator('[data-new-only]').check();await expect(page.locator('[data-no-new]')).toBeVisible();
 await page.reload();await expect(page.locator('[data-new-count]')).toHaveText('0');
});

test('latest correction has real evidence and renders its data',async({page})=>{
 await page.goto('materials/education-programme-correction/');
 await expect(page.getByRole('heading',{level:1})).toContainText(/программ|площад|учеб/i);
 await expect(page.locator('body')).toContainText('197');await expect(page.locator('body')).toContainText('19');
 const sourceCommit=JSON.parse(readFileSync(new URL('../content/materials/education-programme-correction.json',import.meta.url),'utf8')).sourceCommit;const sources=page.locator(`a[href*="${sourceCommit}"]`);expect(await sources.count()).toBeGreaterThan(0);
 await expect(page.locator('[data-visual-id]').first()).toBeVisible();
 await page.locator('[data-visual-id]').first().scrollIntoViewIfNeeded();await expect(page.locator('[data-visual-id] svg').first()).toBeVisible();
});

test('map selection, layers, plots and deep links work on real data',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('map/?layers=population,regions,centres');
 const search=page.getByRole('textbox',{name:'Поиск места или территории'});await expect(search).toBeVisible();
 await expect(page.locator('.map-loading')).toHaveCount(0,{timeout:75000});
 await search.fill('Уральск');await expect(page.locator('.map-search-results button').first()).toBeVisible();
 await page.locator('.map-search-results button').first().click();await expect(page.locator('.map-infographic h2')).toContainText('Уральск');
 await expect(page.locator('.map-infographic svg').first()).toBeVisible();await expect(page).toHaveURL(/selection=/);
 const selectedUrl=page.url();await page.reload();await expect(page.locator('.map-infographic h2')).toContainText('Уральск',{timeout:75000});
 await page.getByRole('button',{name:'Закрыть выбранный объект'}).click();await search.fill('Учалинский');await expect(page.locator('.map-search-results button').first()).toBeVisible();
 const district=page.locator('.map-search-results button').filter({hasText:/Район/}).first();await district.click();
 await expect(page.locator('.map-infographic h2')).toContainText(/Uchal|Учалин/);await expect(page.locator('.map-infographic')).toContainText('пространствен',{ignoreCase:true});
 await expect(page.locator('.map-infographic svg').first()).toBeVisible();expect(selectedUrl).toContain('mode=settlement');expect(errors).toEqual([]);
});

test('mobile reading and catalog have no horizontal overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 for(const route of ['atlas/','knowledge/','materials/strict-centres/']){
  await page.goto(route);await expect(page.getByRole('heading',{level:1})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
 }
});

test('a declarative research layer loads once and carries its scientific context',async({page})=>{
 let requests=0;page.on('request',r=>{if(r.url().includes('/custom-layers/centre-surroundings.geojson'))requests++});
 await page.goto('map/?layers=population,centre-surroundings&research=sgrt');
 const toggle=page.locator('[data-layer-id="centre-surroundings"]');await expect(toggle).toBeChecked();
 const legend=page.getByRole('complementary',{name:'Легенда исследовательских слоёв'});
 await expect(legend).toContainText('197 объектов',{timeout:75000});await expect(legend).toContainText('Модельная оценка');await expect(legend.getByRole('link')).toHaveAttribute('href',/3edc853c/);
 await toggle.uncheck();await expect(page).not.toHaveURL(/layers=[^&]*centre-surroundings/);await toggle.check();await expect(legend).toContainText('197 объектов');expect(requests).toBe(1);
});

test('editorial screens have no serious automated accessibility findings',async({page})=>{
 const {default:AxeBuilder}=await import('@axe-core/playwright');
 for(const route of ['atlas/','knowledge/','materials/education-programme-correction/']){
  await page.goto(route);const report=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
  expect(report.violations.filter(v=>['serious','critical'].includes(v.impact||''))).toEqual([]);
 }
});

test('overview maps need no JavaScript and keep the same visual inside the article',async({browser,baseURL})=>{
 const context=await browser.newContext({javaScriptEnabled:false,baseURL});const page=await context.newPage();const requests:string[]=[];page.on('request',r=>requests.push(r.url()));
 await page.goto('atlas/');const card=page.locator('[data-material-card][data-material-id="population-base"]');const preview=card.locator('.cartographic-preview');await expect(preview).toHaveAttribute('data-map-variant','change');
 const image=preview.locator('.map-image-light');await image.scrollIntoViewIfNeeded();await expect.poll(()=>image.evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0)).toBe(true);const source=await image.getAttribute('src');
 const href=await card.locator('h2 a').getAttribute('href');await page.goto(href!);const full=page.locator('[data-visual-id="population-map"] .cartographic-preview');await expect(full).toHaveAttribute('data-map-variant','change');await expect(full.locator('.map-image-light')).toHaveAttribute('src',source!);
 expect(requests.some(url=>/settlements-preview|country-preview|MapThumbnail.*\.js/.test(url))).toBe(false);
 await page.setViewportSize({width:390,height:844});await page.goto('atlas/');
 for(const theme of ['light','dark']){
  await page.locator('html').evaluate((el,value)=>el.setAttribute('data-theme',value),theme);
  for(const select of await page.locator('.toolbar select').all()){
   const style=await select.evaluate(el=>{const s=getComputedStyle(el);return{padding:parseFloat(s.paddingRight),appearance:s.appearance,repeat:s.backgroundRepeat,size:s.backgroundSize,image:s.backgroundImage}});
   expect(style.padding).toBeGreaterThanOrEqual(30);expect(style.appearance).toBe('none');expect(style.repeat).toBe('no-repeat');expect(style.size).toBe('16px 16px');expect(style.image).toContain('data:image/svg+xml');
  }
 }

 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);await context.close();
});

test('current boundaries show native Russian names and the actual source year',async({page},testInfo)=>{
 await page.goto('map/?layers=population,regions');
 const search=page.getByRole('textbox',{name:'Поиск места или территории'});await expect(search).toBeVisible();await expect(page.locator('.map-loading')).toHaveCount(0,{timeout:75000});
 await search.fill('Ишимбайский');const result=page.locator('.map-search-results button').filter({hasText:'Район / округ'}).filter({hasText:'Ишимбайский район'}).first();await expect(result).toBeVisible({timeout:75000});await result.click();
 await expect(page.locator('.map-infographic h2')).toHaveText('Ишимбайский район');await expect(page.locator('.map-info-header')).toContainText('Сетка 2026 года');await expect(page.locator('.map-boundary-note')).toContainText('28.09.2026');
 await expect(page.locator('.map-info-header')).not.toContainText('Ishimbaysky');await expect(page.locator('.map-infographic svg').first()).toBeVisible();
 await page.screenshot({path:testInfo.outputPath('ishimbay-current-grid.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:testInfo.outputPath('ishimbay-current-grid-mobile.png'),fullPage:true});
});

test('mini maps zoom and pan with readable scale labels without loading the full atlas',async({page},testInfo)=>{
 const errors:string[]=[],requests:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
 await page.goto('materials/population-base/');const map=page.locator('[data-mini-map]').first();await map.scrollIntoViewIfNeeded();await expect(map).toHaveClass(/mini-map-ready/);
 const plus=map.getByRole('button',{name:'Приблизить мини-карту',exact:true});for(let i=0;i<3;i++)await plus.click();await expect(map.locator('.mini-map-labels text').first()).toBeVisible();await expect(map).toHaveAttribute('data-mini-label-level','50000');
 const font=await map.evaluate(el=>getComputedStyle(el.querySelector('.mini-map-labels text')!).fontSize);const point=await map.locator('.mini-map-place circle').first().boundingBox();expect(point).not.toBeNull();
 await page.mouse.dblclick(point!.x+point!.width/2,point!.y+point!.height/2);await expect.poll(async()=>Number(await map.getAttribute('data-mini-zoom'))).toBeGreaterThan(10);
 await expect.poll(()=>map.locator('.mini-map-labels text').count()).toBeGreaterThan(0);await expect.poll(()=>map.evaluate(el=>getComputedStyle(el.querySelector('.mini-map-labels text')!).fontSize)).toBe(font);
 const box=await map.locator('.mini-map-surface').boundingBox();const previous=await map.getAttribute('data-mini-x');await page.mouse.move(box!.x+box!.width/2,box!.y+box!.height/2);await page.mouse.down();await page.mouse.move(box!.x+box!.width/2-90,box!.y+box!.height/2+20,{steps:6});await page.mouse.up();await expect.poll(()=>map.getAttribute('data-mini-x')).not.toBe(previous);
 const zoom=await map.getAttribute('data-mini-zoom');await page.locator('#theme-toggle').click();await expect(map).toHaveAttribute('data-mini-zoom',zoom!);await map.scrollIntoViewIfNeeded();await map.screenshot({path:testInfo.outputPath('mini-map-dark-zoom.png')});
 await map.getByRole('button',{name:'Показать всю мини-карту'}).click();await expect(map).toHaveAttribute('data-mini-zoom','1.00');
 const visible=await map.locator('.mini-map-surface').boundingBox();const before=await page.evaluate(()=>scrollY);await page.mouse.move(visible!.x+visible!.width/2,visible!.y+visible!.height/2);await page.mouse.wheel(0,160);await expect.poll(()=>page.evaluate(()=>scrollY)).toBeGreaterThan(before);await expect(map).toHaveAttribute('data-mini-zoom','1.00');
 expect(requests.filter(url=>/mini-map-labels-.*\.json/.test(url))).toHaveLength(1);expect(requests.filter(url=>/settlements\.compact|regions-display|districts-display/.test(url))).toHaveLength(0);expect(errors).toEqual([]);
});

test('multiple mini maps keep independent views and share the small label source',async({page},testInfo)=>{
 let labels=0;page.on('request',r=>{if(/mini-map-labels-.*\.json/.test(r.url()))labels++});await page.goto('');const maps=page.locator('[data-mini-map]');const hero=maps.nth(0),topic=maps.nth(1);
 await hero.getByRole('button',{name:'Приблизить мини-карту',exact:true}).click();await expect(hero.locator('.mini-map-labels text').first()).toBeVisible();await expect(topic).toHaveAttribute('data-mini-zoom','1');
 await topic.getByRole('button',{name:'Приблизить мини-карту',exact:true}).click();await expect(topic.locator('.mini-map-labels text').first()).toBeVisible();await expect(hero).toHaveAttribute('data-mini-zoom','1.80');
 await topic.getByRole('button',{name:'Показать всю мини-карту'}).click();await expect(topic).toHaveAttribute('data-mini-zoom','1.00');await expect(hero).toHaveAttribute('data-mini-zoom','1.80');expect(labels).toBe(1);
 const ids=await page.locator('.mini-map-svg [id]').evaluateAll(nodes=>nodes.map(n=>n.id));expect(new Set(ids).size).toBe(ids.length);await hero.screenshot({path:testInfo.outputPath('mini-map-home.png')});
});

test('mini map supports two-finger zoom on mobile without zooming the page',async({browser,baseURL},testInfo)=>{
 const context=await browser.newContext({baseURL,viewport:{width:390,height:844},isMobile:true,hasTouch:true});const page=await context.newPage();await page.goto('materials/population-base/');const map=page.locator('[data-mini-map]').first();await map.scrollIntoViewIfNeeded();await expect(map).toHaveClass(/mini-map-ready/);const box=await map.locator('.mini-map-surface').boundingBox();const x=box!.x+box!.width/2,y=box!.y+box!.height/2;const cdp=await context.newCDPSession(page);
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:x-30,y},{x:x+30,y}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x-65,y},{x:x+65,y}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 await expect.poll(async()=>Number(await map.getAttribute('data-mini-zoom'))).toBeGreaterThan(1.8);expect(await page.evaluate(()=>visualViewport!.scale)).toBe(1);await expect(map.locator('.mini-map-labels text').first()).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);await map.screenshot({path:testInfo.outputPath('mini-map-mobile-pinch.png')});await context.close();
});
