import {test,expect} from '@playwright/test';

test('GOST figure captions and bracket citations identify the actual dataset',async({page})=>{
 await page.goto('materials/map-reading-guide/');const figure=page.locator('[data-visual-id="population-map"]');await expect(figure.locator('.document-figure-caption')).toHaveText(/^Рисунок 1 — /);await expect(figure.locator('.document-figure-source')).toContainText('Источник: построено автором по данным Связанная база переписей');
 const reference=page.locator('article [data-figure-ref="population-map"]');await expect(reference).toHaveText('рисунок 1');await reference.click();await expect(figure).toBeInViewport();
 const cite=figure.locator('[data-citation-url]');await expect(cite).toHaveText(/^\[\d+\]$/);const target=await cite.getAttribute('href');await cite.click();const source=page.locator(target!);await expect(source).toBeInViewport();await expect(source).toContainText('Связанная база переписей');await expect(source.locator('a')).toHaveAttribute('href',/releases\/tag\/sgrt-census-population-/);
 await expect(page.locator('.document-bibliography')).toHaveCSS('list-style-type','decimal');const bibliography=page.locator('.document-bibliography li');const urls=await bibliography.evaluateAll(els=>els.map(e=>(e as HTMLElement).dataset.bibliographyUrl));expect(new Set(urls).size).toBe(urls.length);await expect(source).toContainText('дата обращения:');
});

test('link placeholders are not numbered drawings and genuine figures keep a continuous counter',async({page})=>{
 await page.goto('materials/uchaly-local-services/');const link=page.locator('[data-figure-kind="link"]');await expect(link).toHaveAttribute('data-visual-id','uchaly-links');await expect(link).not.toHaveAttribute('data-figure-number');await expect(link.locator('.document-figure-caption')).toHaveText(/^Интерактивная карта — /);const chart=page.locator('[data-visual-id="uchaly-demography"]');await expect(chart).toHaveAttribute('data-figure-number','1');await expect(chart.locator('.document-figure-caption')).toHaveText(/^Рисунок 1 — /);
});

test('Word links download real generated documents for the article and the full research',async({page,request})=>{
 for(const [route,selector]of [['materials/map-reading-guide/','[data-word-download]'],['research/population/','[data-research-word]']]){await page.goto(route);const href=await page.locator(selector).getAttribute('href');expect(href).toMatch(/\.docx$/);const response=await request.get(href!);expect(response.ok()).toBe(true);const bytes=await response.body();expect(bytes.subarray(0,2).toString()).toBe('PK');expect(bytes.length).toBeGreaterThan(10000)}
});
