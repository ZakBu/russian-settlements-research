import {readFileSync} from 'node:fs';
import {test,expect} from '@playwright/test';

test('legacy entry points share the complete search and preserve query and research',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 for(const route of ['knowledge/','atlas/']){
  await page.goto(route+'?research=population&q=точности');
  await expect(page.getByRole('heading',{name:'Материалы',exact:true})).toBeVisible();
  await expect.poll(()=>new URL(page.url()).pathname.endsWith('/materials/')).toBe(true);
  const url=new URL(page.url());expect(url.searchParams.get('research')).toBe('population');expect(url.searchParams.get('q')).toBe('точности');
  await expect(page.locator('#materials-search')).toHaveValue('точности');
  const visible=route==='atlas/'?page.locator('[data-material-card]:visible'):page.locator('[data-material-list]:visible');
  await expect(visible).toHaveCount(1);await expect(visible).toContainText('Покрытие населения не равно точности связи');
  await expect(page.locator('[data-material-count]')).toHaveText('Найдено материалов: 1');
 }
 expect(errors).toEqual([]);
});

test('filters and result context survive reload and a round trip through an article',async({page})=>{
 await page.goto('materials/?research=population&tag=data-quality&kind=method&format=chart&q=точности');
 const result=page.locator('[data-material-list]:visible');await expect(result).toHaveCount(1);await expect(result).toContainText('Покрытие населения не равно точности связи');
 const selectedURL=page.url();await page.reload();await expect(page.locator('#materials-search')).toHaveValue('точности');
 await expect(page.getByRole('combobox',{name:'Тип материала',exact:true})).toHaveValue('method');await expect(page.getByRole('combobox',{name:'Формат материала',exact:true})).toHaveValue('chart');
 await expect(page.locator('[data-active-filters]')).toContainText('Качество данных');await expect(result).toHaveCount(1);
 await result.locator('h2 a').click();await expect(page.getByRole('heading',{level:1})).toHaveText('Покрытие населения не равно точности связи');
 await expect(page.getByRole('navigation',{name:'Основная навигация'}).getByRole('link',{name:'Материалы',exact:true})).toHaveAttribute('aria-current','page');
 await page.locator('[data-materials-return]').click();await expect(page).toHaveURL(selectedURL);await expect(page.locator('#materials-search')).toHaveValue('точности');await expect(page.locator('[data-material-list]:visible')).toHaveCount(1);
});

test('list and cards show identical filtered documents and share the same tags',async({page})=>{
 await page.goto('materials/?tag=data-quality');const rows=page.locator('[data-material-list]:visible');await expect.poll(()=>rows.count()).toBeGreaterThan(3);
 const ids=await rows.evaluateAll(els=>els.map(el=>(el as HTMLElement).dataset.materialList).sort());
 await page.getByRole('button',{name:'Карточки',exact:true}).click();await expect(page).toHaveURL(/view=cards/);
 const cards=page.locator('[data-material-card]:visible');await expect(cards).toHaveCount(ids.length);
 expect(await cards.evaluateAll(els=>els.map(el=>(el as HTMLElement).dataset.materialId).sort())).toEqual(ids);
 await page.getByRole('button',{name:'Список',exact:true}).click();await expect(page.locator('[data-material-list]:visible')).toHaveCount(ids.length);await expect(page.locator('[data-active-filters]')).toContainText('Качество данных');
 await page.locator('[data-catalog-preset="all"]').click();await expect(page.locator('[data-active-filters]')).toBeEmpty();await expect.poll(()=>page.locator('[data-material-list]:visible').count()).toBeGreaterThan(ids.length);
});

test('graph exposes real directed references and an accessible local neighbourhood',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('materials/?view=graph');
 const graph=page.getByRole('region',{name:'Связи материалов'});await expect(graph).toBeVisible();await expect(graph.locator('[data-graph-links]>li')).toHaveCount(await page.locator('[data-material-list]').count());
 const data=await page.locator('#materials-data').evaluate(el=>JSON.parse(el.textContent!));
 expect(data.edges.some((e:{source:string;target:string;type:string})=>e.source==='map-reading-guide'&&e.target==='population-coverage'&&e.type==='reference')).toBe(true);
 for(const edge of data.edges){
  const original=JSON.parse(readFileSync(new URL(`../content/materials/${edge.source}.json`,import.meta.url),'utf8'));
  if(edge.type==='reference')expect(original.body).toMatch(new RegExp('\\[\\['+edge.target+'(?:[#|\\]])|\\]\\((?:[^\\s)]*/)?materials/'+edge.target+'(?:[/#)]|\\s)'));
  else if(edge.type==='supersedes')expect(original.supersedes).toBe(edge.target);
  else throw new Error('Unexpected generated relation: '+edge.type);
 }
 await graph.getByRole('combobox',{name:'Документ для локального графа'}).selectOption('population-base');
 await expect(graph.locator('[data-graph-links]>li')).toHaveCount(1);await expect(graph.locator('[data-graph-status]')).toContainText('Явных связей: 0');
 await graph.locator('[data-graph-links]>li>button').click();await expect(graph.locator('[data-graph-preview]')).toContainText('Три переписи в одной связанной базе');await expect(graph.getByRole('link',{name:'Открыть материал →'})).toHaveAttribute('href',/materials\/population-base\//);
 await graph.getByRole('combobox',{name:'Документ для локального графа'}).selectOption('map-reading-guide');await expect(graph.locator('[data-graph-links]>li')).toHaveCount(3);await expect(graph.locator('[data-graph-status]')).toContainText('Явных связей: 3');
 await expect(graph.locator('[data-graph-canvas] svg')).toBeVisible();expect(errors).toEqual([]);
});

test('unread material versions persist across visits and can be marked independently',async({page})=>{
 await page.goto('updates/');const count=page.locator('[data-new-count]');await expect.poll(async()=>Number(await count.textContent())).toBeGreaterThan(2);
 const initial=Number(await count.textContent());await page.reload();await expect(count).toHaveText(String(initial));
 const item=page.locator('[data-update-item]').first(),id=await item.getAttribute('data-material-id');await item.locator('[data-mark-one]').click();await expect(count).toHaveText(String(initial-1));await expect(item.locator('[data-mark-one]')).toHaveText('Просмотрено');
 await page.reload();await expect(count).toHaveText(String(initial-1));
 // Simulate a previously read older revision. A changed scientific revision must reappear.
 await page.evaluate(id=>{const value=JSON.parse(localStorage.getItem('atlas-read-versions')||'{}');value[id!]='older-scientific-version';localStorage.setItem('atlas-read-versions',JSON.stringify(value))},id);
 await page.reload();await expect(count).toHaveText(String(initial));
 await page.getByRole('button',{name:'Отметить всё просмотренным',exact:true}).click();await expect(count).toHaveText('0');await page.locator('[data-new-only]').check();await expect(page.locator('[data-no-new]')).toBeVisible();await page.reload();await expect(count).toHaveText('0');
});

test('desktop outline starts at the article title and keeps its position while scrolling',async({page},testInfo)=>{
 await page.goto('materials/map-reading-guide/');await page.evaluate(()=>document.fonts.ready);
 const title=page.getByRole('heading',{level:1}),outline=page.locator('.document-toc-left nav');await expect(outline).toBeVisible();
 const initial=(await outline.boundingBox())!.y,titleTop=(await title.boundingBox())!.y;expect(Math.abs(initial-titleTop)).toBeLessThanOrEqual(3);
 await page.screenshot({path:testInfo.outputPath('outline-title-aligned.png')});
 for(const top of [500,1000]){await page.evaluate(top=>{document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,top)},top);await expect.poll(async()=>Math.abs((await outline.boundingBox())!.y-initial)).toBeLessThanOrEqual(3);}
 await page.screenshot({path:testInfo.outputPath('outline-fixed-after-scroll.png')});
});
