import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
test('collections are the first entry, share the selector, and expose real hierarchy',async({page},testInfo)=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('materials/');
 await expect(page.locator('[data-collection-hub]')).toBeVisible();await expect(page.locator('[data-collection-open]')).toHaveCount(3);await expect(page.locator('#materials-results')).toBeHidden();
 await page.screenshot({path:testInfo.outputPath('collections-home.png')});
 await page.locator('[data-collection-open=population]').click();await expect(page.locator('#research-switch')).toHaveValue('population');await expect(page.locator('[data-collection-context]')).toContainText('Население и расселение');
 await expect(page.locator('[data-materials-tree]')).toBeVisible();await page.locator('[data-page-tree-branch=population-base]>summary').click();await expect(page.locator('[data-page-tree-node=population-comparability]')).toBeVisible();
 await page.screenshot({path:testInfo.outputPath('collection-hierarchy.png')});
 await page.locator('#research-switch').selectOption('ecommerce');await expect(page.locator('[data-collection-context]')).toContainText('Маркетплейсы и центры');
 await page.getByRole('navigation',{name:'Основная навигация'}).getByRole('link',{name:'Карта',exact:true}).click();await expect(page).toHaveURL(/research=ecommerce/);await expect(page.locator('#research-switch')).toHaveValue('ecommerce');expect(errors).toEqual([]);
});
test('graph distinguishes collections and explicit parent links',async({page},testInfo)=>{
 await page.goto('materials/?view=graph');await expect(page.locator('[data-graph-canvas] svg')).toBeVisible();
 const data=await page.locator('#materials-data').evaluate(el=>JSON.parse(el.textContent!));expect(data.edges.some((e:{type:string})=>e.type==='hierarchy')).toBe(true);
 const graph=page.locator('[data-graph-canvas]');for(const title of ['Население и расселение','Районы тяготения','Маркетплейсы и центры'])await expect(graph).toContainText(title);
 await page.screenshot({path:testInfo.outputPath('collections-graph.png')});
});
test('collection navigation works on mobile in light and dark without overflow',async({page},testInfo)=>{
 await page.setViewportSize({width:390,height:844});await page.goto('materials/');
 for(const theme of ['light','dark']){
  if(theme==='dark')await page.locator('#theme-toggle').click();
  await expect(page.locator('#research-switch')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const scan=await new AxeBuilder({page}).analyze();expect(scan.violations.filter(v=>['serious','critical'].includes(v.impact||''))).toEqual([]);
  await page.screenshot({path:testInfo.outputPath(`collections-mobile-${theme}.png`),fullPage:true});
 }
});
