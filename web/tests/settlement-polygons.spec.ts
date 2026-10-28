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
 await expect(page.locator('.map-info-context')).toContainText('Переписных точек в базе');await expect(page.locator('.map-info-context')).toContainText('Картографический контур');
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
 await page.mouse.move(900,350);await page.mouse.wheel(0,500);await page.waitForTimeout(1000);const before=Number(new URL(page.url()).searchParams.get('zoom'));
 release();await expect(page.locator('[data-settlement-boundary]')).toHaveAttribute('data-settlement-boundary','available');await page.waitForTimeout(800);expect(Number(new URL(page.url()).searchParams.get('zoom'))).toBeCloseTo(before,1);
});
