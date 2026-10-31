import {test,expect} from '@playwright/test';
const kazan='51fc2a397de5f7a2';
test('Kazan selects a real settlement polygon lazily while census statistics remain attached to the city',async({page},testInfo)=>{
 const requests:string[]=[],errors:string[]=[];page.on('request',r=>requests.push(r.url()));page.on('pageerror',e=>errors.push(e.message));
 await page.goto('map/');await expect(page.locator('.map-place-label').first()).toBeVisible({timeout:75000});expect(requests.some(url=>url.includes('settlement-polygons/'))).toBe(false);
 const search=page.getByRole('textbox',{name:'Поиск места или территории'});await search.fill('Казань');
 await page.locator('.map-search-results button').filter({hasText:'Казань'}).filter({hasText:'Татарстан'}).first().click();
 await expect(page.locator('.map-infographic h2')).toHaveText('Казань');await expect(page.locator('[data-settlement-boundary]')).toHaveAttribute('data-settlement-boundary','available',{timeout:30000});
 expect(requests.filter(url=>url.includes('settlement-polygons/51.json'))).toHaveLength(1);
 const response=await page.request.get(`data/settlement-polygons/51.json`);const records=await response.json();const polygon=records[kazan];expect(polygon.geometry.type).toMatch(/Polygon/);expect(polygon.properties.id).toBe(kazan);expect(JSON.stringify(polygon.properties)).toMatch(/OpenStreetMap|Geofabrik|OSM/);
 await expect(page.locator('.map-charts')).toHaveAttribute('aria-label','Население выбранного пункта по трём переписям');await expect(page.locator('.map-summary-answer')).toContainText('2002–2021');await expect(page.locator('.map-info-context')).toContainText('Картографический контур');
 await page.waitForTimeout(800);await page.screenshot({path:testInfo.outputPath('kazan-polygon.png')});
 await page.locator('#theme-toggle').click();await page.waitForTimeout(250);await page.screenshot({path:testInfo.outputPath('kazan-polygon-dark.png')});await expect(page.locator('[data-settlement-boundary]')).toHaveAttribute('data-settlement-boundary','available');expect(errors).toEqual([]);
});
test('a delayed contour never replaces a new selection or returns after close',async({page})=>{
 let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);let started=false;
 await page.route('**/settlement-polygons/51.json',async route=>{started=true;await gate;await route.continue()});
 await page.goto(`map/?selection=${kazan}&mode=settlement&zoom=10&lat=55.8&lng=49.1`);await expect(page.locator('.map-infographic h2')).toHaveText('Казань',{timeout:75000});await expect.poll(()=>started).toBe(true);
 await page.getByRole('button',{name:'Закрыть выбранный объект'}).click();release();await page.waitForTimeout(500);await expect(page.locator('.map-infographic')).toHaveCount(0);await expect(page).not.toHaveURL(/selection=/);
});

test('manual map movement cancels a delayed automatic city fit',async({page})=>{
 let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);let started=false;
 await page.route('**/settlement-polygons/51.json',async route=>{started=true;await gate;await route.continue()});
 await page.goto('map/');const search=page.getByRole('textbox',{name:'Поиск места или территории'});await search.fill('Казань');await page.locator('.map-search-results button').filter({hasText:'Казань'}).filter({hasText:'Татарстан'}).first().click();await expect.poll(()=>started).toBe(true);
 // A visible canvas must fill the resized stage; a clipped zero-height MapLibre
 // container can otherwise make this wheel gesture hit the background instead.
 const canvas=page.locator('.map-canvas');
 await expect.poll(async()=>{const box=await canvas.boundingBox(),stage=await page.locator('.map-stage').boundingBox();return box&&stage?Math.abs(box.height-stage.height):Infinity;}).toBeLessThan(1);
 await expect.poll(()=>Number(new URL(page.url()).searchParams.get('zoom'))).toBe(11);
 const box=(await canvas.boundingBox())!,x=box.x+box.width*.6,y=box.y+box.height*.45;
 expect(await page.evaluate(({x,y})=>Boolean(document.elementFromPoint(x,y)?.closest('.maplibregl-canvas-container')),{x,y})).toBe(true);
 const initial=Number(new URL(page.url()).searchParams.get('zoom'));
 await page.mouse.move(x,y);await page.mouse.wheel(0,500);
 await expect.poll(()=>Number(new URL(page.url()).searchParams.get('zoom'))).toBeLessThan(initial);
 await page.waitForTimeout(1000);const before=Number(new URL(page.url()).searchParams.get('zoom'));
 release();await expect(page.locator('[data-settlement-boundary]')).toHaveAttribute('data-settlement-boundary','available');await page.waitForTimeout(800);expect(Number(new URL(page.url()).searchParams.get('zoom'))).toBeCloseTo(before,1);
});
