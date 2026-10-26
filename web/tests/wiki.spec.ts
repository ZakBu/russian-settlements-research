import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('library finds words inside documents, filters kinds and recovers from no results',async({page})=>{
 await page.goto('knowledge/');const entries=page.locator('[data-material-list]:visible');const total=await entries.count();expect(total).toBeGreaterThan(10);
 const search=page.getByRole('searchbox',{name:'Поиск материалов'});await search.fill('зимники');await expect(entries).toHaveCount(1);await expect(entries).toContainText('Модельное направление');
 await search.fill('');await page.getByRole('combobox',{name:'Тип материала',exact:true}).selectOption('method');await expect.poll(()=>entries.count()).toBeGreaterThan(2);expect(await entries.locator('.eyebrow').evaluateAll(els=>els.every(el=>el.textContent?.startsWith('Метод и понятия /')))).toBe(true);await expect(page.getByRole('combobox',{name:'Тип материала',exact:true})).toHaveValue('method');
 await search.fill('несуществующий-документ-xyz');await expect(entries).toHaveCount(0);await page.getByRole('button',{name:'Сбросить поиск и фильтры'}).click();await expect(entries).toHaveCount(total);await expect(search).toBeFocused();
 await page.keyboard.press('Escape');await search.blur();await page.keyboard.press('/');await expect(search).toBeFocused();
});

test('documents connect headings, inline maps, disclosures, footnotes and backlinks',async({page},testInfo)=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('materials/map-reading-guide/');
 const heading=page.getByRole('heading',{level:1});await expect(heading).toHaveText('Как читать карту и её слои');expect((await heading.boundingBox())!.height).toBeLessThan(180);
 const textBox=await page.locator('.document-body').boundingBox();const outlineBox=await page.locator('.document-toc-left').boundingBox();expect(outlineBox!.x+outlineBox!.width).toBeLessThan(textBox!.x);expect(textBox!.width).toBeLessThanOrEqual(701);
 const toc=page.getByRole('navigation',{name:'На этой странице',exact:true});await toc.getByRole('link',{name:'Территориальная сетка',exact:true}).click();await expect(page).toHaveURL(/#.*сетка|#.*D1%81%D0%B5%D1%82%D0%BA%D0%B0/i);await expect(page.locator('#территориальная-сетка')).toBeInViewport();
 const disclosure=page.locator('details.document-details');await expect(disclosure).not.toHaveAttribute('open');await disclosure.locator('summary').click();await expect(disclosure).toHaveAttribute('open','');await expect(disclosure).toContainText('28 сентября 2026 года');
 const footnote=disclosure.locator('sup a');await expect(footnote).toHaveCount(1);await footnote.click();await expect(page.locator('.footnotes')).toBeInViewport();
 await page.locator('.footnotes a[aria-label="Вернуться к упоминанию сноски"]').click();await expect(disclosure).toHaveAttribute('open','');
 const map=page.locator('[data-visual-id="population-map"]');await map.scrollIntoViewIfNeeded();await expect(map).toBeVisible();const afterMap=await page.locator('#территориальная-сетка').boundingBox();expect(afterMap!.y).toBeGreaterThan((await map.boundingBox())!.y);
 await disclosure.scrollIntoViewIfNeeded();await page.screenshot({path:testInfo.outputPath('wiki-disclosure-light.png')});await page.locator('#theme-toggle').click();await page.screenshot({path:testInfo.outputPath('wiki-disclosure-dark.png')});
 await page.locator('article .wiki-link[href$="/model-and-observation/"]').click();await expect(page.getByRole('heading',{name:'На этот документ ссылаются',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'Что даёт модель',exact:false})).toBeVisible();
 expect(errors).toEqual([]);
});

test('wiki mobile navigation, contrast and no-JavaScript reading remain usable',async({page,browser},testInfo)=>{
 await page.setViewportSize({width:390,height:844});await page.goto('knowledge/');const menu=page.locator('.document-library-menu');await expect(menu).not.toHaveAttribute('open');await menu.locator(':scope > summary').click();await expect(menu).toHaveAttribute('open','');await menu.locator(':scope > summary').click();await page.goto('materials/map-reading-guide/');
 const toc=page.locator('.document-mobile-toc');await toc.locator('summary').click();await toc.getByRole('link',{name:'Услуги и связи',exact:true}).click();await expect(page.locator('#услуги-и-связи')).toBeInViewport();await page.screenshot({path:testInfo.outputPath('wiki-mobile.png')});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 for(const dark of [false,true]){if(dark)await page.locator('#theme-toggle').click();const audit=await new AxeBuilder({page}).analyze();expect(audit.violations.filter(v=>['serious','critical'].includes(v.impact||''))).toEqual([])}
 await page.goto('materials/model-and-observation/');const modelAudit=await new AxeBuilder({page}).analyze();expect(modelAudit.violations.filter(v=>['serious','critical'].includes(v.impact||''))).toEqual([]);
 const context=await browser.newContext({javaScriptEnabled:false});const staticPage=await context.newPage();await staticPage.goto(new URL('materials/map-reading-guide/',page.url().split('materials/')[0]).href);await expect(staticPage.getByRole('heading',{level:1})).toBeVisible();await expect(staticPage.getByRole('navigation',{name:'На этой странице',exact:true})).toBeVisible();await staticPage.locator('details.document-details summary').click();await expect(staticPage.locator('details.document-details')).toHaveAttribute('open','');await context.close();
});
