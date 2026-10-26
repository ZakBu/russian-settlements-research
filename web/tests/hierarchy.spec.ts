import {test,expect} from '@playwright/test';

test('a section includes every descendant and keeps the selected branch across views and reload',async({page})=>{
 await page.goto('materials/?within=population-base');
 const data=await page.locator('#materials-data').evaluate(el=>JSON.parse(el.textContent!));
 const expected=data.rows.filter((r:{id:string;ancestors:string[]})=>r.id==='population-base'||r.ancestors.includes('population-base')).map((r:{id:string})=>r.id).sort();
 expect(expected).toContain('population-coverage');expect(expected).toContain('population-comparability');
 const rows=page.locator('[data-material-list]:visible');await expect(rows).toHaveCount(expected.length);
 expect(await rows.evaluateAll(es=>es.map(e=>(e as HTMLElement).dataset.materialList).sort())).toEqual(expected);
 await expect(page.locator('[data-active-filters]')).toContainText('Раздел: Три переписи');
 await expect(page.locator('[data-page-tree-branch="population-base"]')).toHaveAttribute('open','');
 await page.getByRole('button',{name:'Карточки',exact:true}).click();await expect(page.locator('[data-material-card]:visible')).toHaveCount(expected.length);
 await page.reload();await expect(page).toHaveURL(/within=population-base/);await expect(page.locator('[data-material-card]:visible')).toHaveCount(expected.length);
 await page.getByRole('button',{name:'Список',exact:true}).click();await page.getByRole('button',{name:/Убрать условие: Раздел:/}).click();await expect(page).not.toHaveURL(/within=/);
});

test('nested articles have stable URLs, ordered ancestors and real child links',async({page})=>{
 await page.goto('materials/population-coverage/');
 const breadcrumbs=page.getByRole('navigation',{name:'Путь документа'});
 const parents=breadcrumbs.locator('[data-document-ancestor]');await expect(parents).toHaveCount(2);
 expect(await parents.evaluateAll(es=>es.map(e=>(e as HTMLElement).dataset.documentAncestor))).toEqual(['population-base','population-comparability']);
 await parents.last().click();await expect(page).toHaveURL(/\/materials\/population-comparability\//);
 await expect(page.getByRole('region',{name:'В этом разделе'}).getByRole('link',{name:/Покрытие населения/})).toHaveAttribute('href',/materials\/population-coverage\//);
 const heading=await page.locator('h1').boundingBox(),outline=await page.locator('.document-toc-left nav').boundingBox();expect(Math.abs(heading!.y-outline!.y)).toBeLessThan(3);
});

test('native nested page disclosures remain usable on a small screen',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('materials/?within=population-comparability');
 const library=page.locator('.document-library-menu');await library.locator(':scope > summary').click();
 await expect(page.locator('[data-research-tree="population"]')).toHaveAttribute('open','');
 const branch=page.locator('[data-page-tree-branch="population-comparability"]');await expect(branch).toHaveAttribute('open','');
 const child=page.locator('[data-page-tree-node="population-coverage"]>a');await expect(child).toBeVisible();await child.click();await expect(page).toHaveURL(/materials\/population-coverage\//);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
