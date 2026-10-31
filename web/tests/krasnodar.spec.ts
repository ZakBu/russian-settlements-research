import {test,expect} from '@playwright/test';

test('Krasnodar sources isolate actual study geography and retain a shareable state',async({page})=>{
 const failures:string[]=[];page.on('pageerror',error=>failures.push(error.message));
 await page.goto('krasnodar/maps/');
 const studies=page.locator('.kr-study-pick');await expect(studies.first()).toBeVisible();expect(await studies.count()).toBeGreaterThanOrEqual(5);
 await studies.nth(3).click();await expect(page.locator('.kr-layer-check input:checked')).toHaveCount(1);await expect(page.getByRole('button',{name:'Одна граница',exact:true})).toHaveAttribute('aria-pressed','true');
 const title=await studies.nth(3).locator('strong').textContent();await expect(page.locator('.kr-source-panel h2')).toHaveText(title!);await expect(page.locator('.kr-source-link')).toHaveAttribute('href',/^https:\/\//);
 const shared=page.url();expect(shared).toContain('mode=solo');await page.reload();await expect(page.locator('.kr-layer-check input:checked')).toHaveCount(1);await expect(page.locator('.kr-source-panel h2')).toHaveText(title!);
 await page.getByRole('button',{name:'Сравнить границы',exact:true}).click();expect(await page.locator('.kr-layer-check input:checked').count()).toBeGreaterThanOrEqual(5);
 await page.setViewportSize({width:390,height:844});await expect(page.locator('.kr-source-panel h2')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth)).toBeLessThanOrEqual(1);expect(failures).toEqual([]);
});

test('Ten code slides support keyboard navigation, deep links, mobile and complete print geography',async({page})=>{
 await page.goto('krasnodar/presentation/#slide-1');await expect(page.locator('.kr-slide')).toHaveCount(10);await expect(page.locator('.kr-slide:visible')).toHaveCount(1);await expect(page.locator('.kr-slide:visible svg')).toHaveCount(1);
 await page.keyboard.press('ArrowRight');await expect(page).toHaveURL(/#slide-2$/);await expect(page.locator('.kr-slide:visible')).toHaveAttribute('aria-label','Слайд 2 из 10');
 await page.getByRole('button',{name:'Слайды',exact:true}).click();await page.getByRole('button',{name:/07.*Сетевая доступность/}).click();await expect(page).toHaveURL(/#slide-7$/);
 await page.reload();await expect(page.locator('.kr-slide:visible')).toHaveAttribute('aria-label','Слайд 7 из 10');
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth)).toBeLessThanOrEqual(1);
 await page.emulateMedia({media:'print'});await expect(page.locator('.kr-slide:visible')).toHaveCount(10);expect(await page.locator('.kr-slide svg').count()).toBeGreaterThanOrEqual(4);
});
