import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', testMatch: 'production.spec.js', timeout: 60000, workers: 1, outputDir: 'test-results/production',
  use: { baseURL: 'http://127.0.0.1:1441', browserName: 'chromium', channel: process.platform === 'win32' ? 'msedge' : undefined, viewport: { width: 1280, height: 900 }, trace: 'retain-on-failure' },
  webServer: { command: 'npm run preview -- --port 1441 --strictPort', url: 'http://127.0.0.1:1441', reuseExistingServer: false },
});
