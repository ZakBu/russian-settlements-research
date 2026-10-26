import {test,expect} from '@playwright/test';

test('overview avoids the full census download until search, and remains readable without the external basemap',async({page})=>{
 const errors:string[]=[],requests:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
 await page.route('https://tiles.openfreemap.org/**',route=>route.abort());
 await page.goto('map/');await expect.poll(()=>requests.some(url=>url.includes('settlements.overview.json')),{timeout:75000}).toBe(true);await expect(page.locator('.map-place-label').first()).toBeVisible({timeout:75000});await expect(page.locator('.map-loading')).toHaveCount(0,{timeout:75000});
 expect(requests.some(url=>url.includes('settlements.overview.json'))).toBe(true);
 expect(requests.some(url=>url.includes('settlements.compact.json'))).toBe(false);
 await expect(page.locator('.map-place-label').first()).toBeVisible();
 const search=page.getByRole('textbox',{name:'Поиск места или территории'});await search.fill('Уральск');await expect(page.locator('.map-search-results button').first()).toBeVisible();
 await page.locator('.map-search-results button').first().click();await expect(page.locator('.map-infographic h2')).toContainText('Уральск');
 expect(requests.filter(url=>url.includes('settlements.compact.json'))).toHaveLength(1);expect(errors).toEqual([]);
});

test('Crimea and Sevastopol have real searchable reference polygons, without inventing population values',async({page})=>{
 await page.goto('map/?mode=region&layers=regions');await expect(page.locator('.map-loading')).toHaveCount(0,{timeout:75000});
 const search=page.getByRole('textbox',{name:'Поиск места или территории'});await search.fill('Крым');
 await page.locator('.map-search-results button').filter({hasText:'Регион'}).filter({hasText:'Крым'}).first().click();
 await expect(page.locator('.map-infographic h2')).toHaveText('Крым');await expect(page.locator('.map-charts')).toContainText('Нет зачтённых данных');
 await page.getByRole('button',{name:'Закрыть выбранный объект'}).click();await search.fill('Севастополь');
 await page.locator('.map-search-results button').filter({hasText:'Регион'}).first().click();await expect(page.locator('.map-infographic h2')).toHaveText('Севастополь');
 await expect(page.locator('.map-charts')).toContainText('Нет зачтённых данных');
});
