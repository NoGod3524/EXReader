import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './tests', outputDir: 'test-results/framework', testMatch: 'framework.spec.js', timeout: 60000, fullyParallel: false, workers: 1,
  use: { baseURL: 'http://127.0.0.1:1430', viewport: { width: 1280, height: 900 }, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium', channel: process.platform === 'win32' ? 'msedge' : undefined, launchOptions: { args: process.platform === 'win32' ? ['--disable-gpu'] : [] } } },
    { name: 'webkit', use: { browserName: 'webkit' } },
    { name: 'mobile', use: { ...devices['iPhone 13'], browserName: 'webkit' } },
  ],
  webServer: { command: 'npx vite --config vite.framework.config.js --host 127.0.0.1', url: 'http://127.0.0.1:1430/tests/blank.html', reuseExistingServer: true },
});
