import {defineConfig,devices} from '@playwright/test';
export default defineConfig({testDir:'./e2e',use:{baseURL:'http://localhost:3000'},webServer:{command:'node node_modules/next/dist/bin/next dev',url:'http://localhost:3000',reuseExistingServer:!process.env.CI},projects:[{name:'chromium',use:{...devices['Desktop Chrome']}}]});
