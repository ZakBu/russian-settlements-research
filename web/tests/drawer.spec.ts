import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('document drawer reuses the nested library with current ancestors and native keyboard focus',async({page},testInfo)=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('materials/population-coverage/');
 const trigger=page.getByRole('button',{name:'Открыть навигацию по материалам',exact:true}),drawer=page.getByRole('dialog',{name:'Материалы и исследования',exact:true});
 await expect(page.locator('[data-page-tree-node]')).toHaveCount(0);await trigger.click();await expect(drawer).toBeVisible();await expect(trigger).toHaveAttribute('aria-expanded','true');
 const close=drawer.getByRole('button',{name:'Закрыть навигацию по материалам',exact:true});await expect(close).toBeFocused();
 await expect(drawer.locator('[data-research-tree="population"]')).toHaveAttribute('open','');
 for(const id of ['population-base','population-comparability'])await expect(drawer.locator(`[data-page-tree-branch="${id}"]`)).toHaveAttribute('open','');
 await expect(drawer.locator('[data-page-tree-node="population-coverage"]>a')).toHaveAttribute('aria-current','page');await expect(drawer.locator('[data-page-tree-node="population-coverage"]>a')).toBeInViewport();
 await page.keyboard.press('Shift+Tab');expect(await drawer.evaluate(el=>el.contains(document.activeElement))).toBe(true);
 for(let i=0;i<8;i++){await page.keyboard.press('Tab');expect(await drawer.evaluate(el=>el.contains(document.activeElement))).toBe(true)}
 await page.screenshot({path:testInfo.outputPath('drawer-current-document.png')});
 await page.keyboard.press('Escape');await expect(drawer).not.toBeVisible();await expect(trigger).toHaveAttribute('aria-expanded','false');await expect(trigger).toBeFocused();await expect(page.locator('[data-page-tree-node]')).toHaveCount(0);expect(errors).toEqual([]);
});

test('catalog tree is unique before and after drawer use and drawer links navigate normally',async({page})=>{
 await page.goto('materials/');const initial=await page.locator('[data-page-tree-node]').count();expect(initial).toBeGreaterThan(10);
 const trigger=page.getByRole('button',{name:'Открыть навигацию по материалам',exact:true});await trigger.click();const drawer=page.getByRole('dialog',{name:'Материалы и исследования',exact:true});await expect(drawer).toBeVisible();
 const width=await page.evaluate(()=>innerWidth);await page.mouse.click(width-8,20);await expect(drawer).not.toBeVisible();await expect(page.locator('[data-page-tree-node]')).toHaveCount(initial);await expect(trigger).toBeFocused();
 await trigger.click();await drawer.locator('[data-catalog-research="ecommerce"]').click();await expect(page).toHaveURL(/materials\/\?research=ecommerce/);await expect(page.locator('[data-collection-context]')).toContainText('Маркетплейсы и центры');await expect(page.locator('[data-collection-tree="ecommerce"]')).toBeVisible();await expect(page.getByRole('dialog')).not.toBeVisible();await expect(page.locator('[data-page-tree-node]')).toHaveCount(initial);
});

test('drawer and article remain usable on mobile in both themes',async({page},testInfo)=>{
 await page.setViewportSize({width:390,height:844});await page.goto('materials/population-coverage/');
 for(const theme of ['light','dark']){
  if(theme==='dark')await page.locator('#theme-toggle').click();
  const trigger=page.getByRole('button',{name:'Открыть навигацию по материалам',exact:true});await trigger.click();const drawer=page.getByRole('dialog',{name:'Материалы и исследования',exact:true});await expect(drawer).toBeVisible();
  const box=(await drawer.boundingBox())!;expect(box.x).toBe(0);expect(box.width).toBeLessThanOrEqual(366);expect(box.height).toBeLessThanOrEqual(845);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const audit=await new AxeBuilder({page}).analyze();expect(audit.violations.filter(v=>['serious','critical'].includes(v.impact||''))).toEqual([]);
  await page.screenshot({path:testInfo.outputPath(`drawer-mobile-${theme}.png`)});await drawer.getByRole('button',{name:'Закрыть навигацию по материалам',exact:true}).click();await expect(trigger).toBeFocused();
 }
 await page.getByRole('button',{name:'Открыть навигацию по материалам',exact:true}).click();await page.getByRole('dialog').getByRole('link',{name:'Все коллекции',exact:true}).click();await expect(page.getByRole('heading',{level:1})).toHaveText('Материалы');
});

test('a long desktop outline scrolls within the viewport without moving the article',async({page})=>{
 await page.goto('materials/map-reading-guide/');const outline=page.locator('.document-toc-left nav');await outline.evaluate(nav=>{for(let i=0;i<60;i++){const link=document.createElement('a');link.href='#document-sources';link.textContent=`Дополнительный раздел ${i+1}`;nav.append(link)}});
 await page.evaluate(()=>{document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,600)});await expect.poll(async()=>Math.abs((await outline.boundingBox())!.y-24)).toBeLessThanOrEqual(2);
 const box=(await outline.boundingBox())!;expect(box.height).toBeLessThanOrEqual(await page.evaluate(()=>innerHeight-48));const scroll=await page.evaluate(()=>scrollY);await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.wheel(0,400);await expect.poll(()=>outline.evaluate(el=>el.scrollTop)).toBeGreaterThan(0);expect(await page.evaluate(()=>scrollY)).toBe(scroll);
});

test('the single drawer trigger remains reachable after scrolling an article',async({page})=>{
 await page.goto('materials/map-reading-guide/');const trigger=page.getByRole('button',{name:'Открыть навигацию по материалам',exact:true});await expect(trigger).toHaveCount(1);
 await page.evaluate(()=>{document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,1000)});await expect(trigger).toBeInViewport();
 const buttonBox=(await trigger.boundingBox())!,outlineBox=(await page.locator('.document-toc-left nav').boundingBox())!;expect(buttonBox.y).toBe(16);expect(buttonBox.x+buttonBox.width).toBeLessThan(outlineBox.x);expect(outlineBox.y).toBe(24);
 await trigger.click();const drawer=page.getByRole('dialog');await expect(drawer).toBeVisible();await page.keyboard.press('Escape');await expect(drawer).not.toBeVisible();await expect(trigger).toBeFocused();expect(await page.evaluate(()=>scrollY)).toBe(1000);
});
