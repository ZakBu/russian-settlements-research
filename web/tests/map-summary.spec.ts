import {test,expect} from '@playwright/test';
const kazan='51fc2a397de5f7a2';
for(const width of [1488,390]) test(`selection reserves map space and restores it on close (${width}px)`,async({page})=>{
 await page.setViewportSize({width,height:900});
 await page.goto(`map/?selection=${kazan}&mode=settlement&zoom=9&lat=55.8&lng=49.1`);
 const sheet=page.locator('.map-infographic');await expect(sheet.locator('h2')).toHaveText('Казань',{timeout:75000});
 await expect(page.locator('.map-summary-answer')).toContainText('2002–2021');
 await expect(page.locator('.map-summary-answer')).toContainText('%');
 await expect(page.locator('.map-charts')).not.toContainText('НП по населению');
 const stage=page.locator('.map-stage'),before=(await stage.boundingBox())!;
 expect(before.height).toBeGreaterThan(240);
 expect(before.y+before.height).toBeLessThanOrEqual((await sheet.boundingBox())!.y+1);
 if(width<760) await page.getByRole('button',{name:'Слои',exact:false}).first().click();
 const layer=await page.locator('.map-layer-panel').boundingBox();expect(layer!.y+layer!.height).toBeLessThanOrEqual((await sheet.boundingBox())!.y+1);
 await page.getByRole('button',{name:'Свернуть графики'}).click();await expect.poll(async()=>(await stage.boundingBox())!.height).toBeGreaterThan(before.height);
 await page.getByRole('button',{name:'Закрыть выбранный объект'}).click();await expect(sheet).toHaveCount(0);
 expect((await stage.boundingBox())!.height).toBeGreaterThan(before.height);
});
test('service-only selection explains evidence instead of showing unrelated population charts',async({page})=>{
 await page.goto('map/?layers=schools&selection=b67ec69836328c8f&mode=settlement&zoom=10&lat=54.12&lng=59.12');
 await expect(page.locator('.map-infographic h2')).toHaveText('Уральск',{timeout:75000});
 await expect(page.locator('.map-summary-content')).toContainText('Документированное прикрепление');
 await expect(page.locator('.map-summary-content')).toContainText('2025');
 await expect(page.locator('.map-summary-content a').first()).toHaveAttribute('href',/^https:/);
 await expect(page.locator('.map-charts')).toHaveCount(0);
 await page.getByRole('button',{name:'Население',exact:true}).click();await expect(page.locator('.map-charts')).toBeVisible();
});

test('territorial figures follow the chosen region and period with explicit coverage',async({page})=>{
 await page.goto('map/?mode=region&layers=population,regions');
 const search=page.getByRole('textbox',{name:'Поиск места или территории'});
 await search.fill('Нижегородская');await page.locator('.map-search-results button').filter({hasText:'Регион'}).first().click();
 await expect(page.locator('.map-summary-note')).toContainText('4 527 из 4 786');
 const first=await page.locator('.map-summary-answer').innerText();
 await page.getByRole('button',{name:'2002–2010',exact:true}).click();
 await expect(page.locator('.map-summary-answer')).toContainText('2002–2010');expect(await page.locator('.map-summary-answer').innerText()).not.toBe(first);
 await search.fill('Татарстан');await page.locator('.map-search-results button').filter({hasText:'Регион'}).first().click();
 await expect(page.locator('.map-infographic h2')).toContainText('Татарстан');expect(await page.locator('.map-summary-answer').innerText()).not.toBe(first);
});

test('region fit uses the viewport after the summary opens',async({page})=>{
 await page.goto('map/');const search=page.getByRole('textbox',{name:'Поиск места или территории'});await search.fill('Крым');
 await page.locator('.map-search-results button').filter({hasText:'Регион'}).filter({has:page.locator('strong',{hasText:/^Крым$/})}).first().click();
 await expect(page.locator('.map-infographic h2')).toHaveText('Крым');
 // Inspect the existing map ref without adding a test-only production API.
 await expect.poll(async()=>page.evaluate(async()=>{
  const canvas=document.querySelector('.map-canvas') as any;
  let fiber=canvas[Object.keys(canvas).find(k=>k.startsWith('__reactFiber'))!], map:any;
  while(fiber&&!map){for(let hook=fiber.memoizedState;hook;hook=hook.next)if(hook.memoizedState?.current?.getStyle){map=hook.memoizedState.current;break}fiber=fiber.return}
  if(!map||map.isMoving())return false;
  const feature=(await map.getSource('selected').getData()).features[0];if(!feature)return false;
  const points:any[]=[];const walk=(a:any)=>{if(typeof a?.[0]==='number')points.push(map.project(a));else if(Array.isArray(a))a.forEach(walk)};walk(feature.geometry.coordinates);
  return points.length>0&&points.every(p=>p.x>=0&&p.x<=map.getCanvas().clientWidth&&p.y>=0&&p.y<=map.getCanvas().clientHeight);
 }),{timeout:15000}).toBe(true);
});
