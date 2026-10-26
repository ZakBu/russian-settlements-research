import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';
const base = process.env.PUBLIC_BASE_PATH || '/';
const baseURL = process.env.SITE_TEST_URL || `http://127.0.0.1:4173${base}`;
export default defineConfig({
 testDir: './tests', timeout: 90000, expect: {timeout:15000}, workers:1,
 reporter: [['list'],['html',{open:'never'}]],
 use:{baseURL,viewport:{width:1488,height:1056},screenshot:'only-on-failure',trace:'retain-on-failure',
 launchOptions:{executablePath:['/usr/bin/chromium','/usr/bin/google-chrome'].find(path=>existsSync(path)),args:['--no-sandbox','--disable-dev-shm-usage','--enable-unsafe-swiftshader']}},
 webServer:process.env.SITE_TEST_URL?undefined:{command:'npm run preview',url:baseURL,reuseExistingServer:!process.env.CI,timeout:45000}
});
