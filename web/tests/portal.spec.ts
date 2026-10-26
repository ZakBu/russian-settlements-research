import {readFileSync} from 'node:fs';
import {test,expect} from '@playwright/test';

test('atlas search, no-results and reset preserve a usable catalogue',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('atlas/');await expect(page.getByRole('heading',{name:'Атлас исследования',exact:true})).toBeVisible();
 const cards=page.locator('[data-material-card]:visible');const total=await cards.count();expect(total).toBeGreaterThan(5);
 await page.getByRole('searchbox',{name:'Поиск материалов'}).fill('197 центров');await expect.poll(()=>cards.count()).toBeGreaterThan(0);
 await page.getByRole('searchbox',{name:'Поиск материалов'}).fill('несуществующий-материал-xyz');await expect(cards).toHaveCount(0);
 await page.getByRole('button',{name:'Сбросить фильтры'}).click();await expect(cards).toHaveCount(total);
 const lead=page.locator('[data-material-card]').first();expect((await lead.boundingBox())!.height).toBeLessThan(850);
 await expect(lead.locator('.cartographic-preview')).toBeVisible();await expect.poll(()=>lead.locator('.map-image-light').evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0)).toBe(true);expect(errors).toEqual([]);
});

test('research selection survives navigation and dark theme survives reload',async({page})=>{
 await page.goto('atlas/');await page.getByRole('combobox',{name:'Выбрать исследование'}).selectOption('ecommerce');await expect(page).toHaveURL(/atlas\/\?research=ecommerce/);
 await expect(page.locator('[data-material-card]:visible')).toHaveCount(2);
 await page.getByRole('navigation',{name:'Основная навигация'}).getByRole('link',{name:'Знания',exact:true}).click();await expect(page).toHaveURL(/knowledge\/\?research=ecommerce/);
 await expect(page.getByRole('combobox',{name:'Выбрать исследование'})).toHaveValue('ecommerce');
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
 await page.goto('atlas/');const card=page.locator('[data-material-card]').first();const preview=card.locator('.cartographic-preview');await expect(preview).toHaveAttribute('data-map-variant','change');
 const image=preview.locator('.map-image-light');await image.scrollIntoViewIfNeeded();await expect.poll(()=>image.evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0)).toBe(true);const source=await image.getAttribute('src');
 const href=await card.locator('h2 a').getAttribute('href');await page.goto(href!);const full=page.locator('[data-visual-id="population-map"] .cartographic-preview');await expect(full).toHaveAttribute('data-map-variant','change');await expect(full.locator('.map-image-light')).toHaveAttribute('src',source!);
 expect(requests.some(url=>/settlements-preview|country-preview|MapThumbnail.*\.js/.test(url))).toBe(false);
 await page.setViewportSize({width:390,height:844});await page.goto('atlas/');
 for(const select of await page.locator('.toolbar select').all()){expect(await select.evaluate(el=>parseFloat(getComputedStyle(el).paddingRight))).toBeGreaterThanOrEqual(30);expect(await select.evaluate(el=>getComputedStyle(el).appearance)).toBe('none')}
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);await context.close();
});
