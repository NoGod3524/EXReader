import { test, expect } from '@playwright/test';
test('production app caches engines and reads books after going offline', async ({ page, context }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('requestfailed', r => errors.push(`${r.url()} ${r.failure()?.errorText}`));
  await page.goto('/');
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    if (registration.active.state !== 'activated') await new Promise(resolve => registration.active.addEventListener('statechange', resolve));
  });
  await page.getByRole('button', { name: '先读一篇示例文章 →' }).click();
  await expect(page.locator('.book-card')).toHaveCount(1);
  await context.setOffline(true); await page.reload();
  expect(errors).toEqual([]);
  await expect(page.locator('.book-card')).toHaveCount(1);
  await page.locator('.book-open').click();
  await expect.poll(() => page.evaluate(() => document.querySelector('foliate-view')?.renderer?.getContents().some(({ doc }) => doc.body?.textContent.includes('窗外的风')) || false)).toBe(true);
  await page.locator('[data-action="back"]').click();
  await page.screenshot({ path: 'docs/screenshots/library.png', fullPage: true });
});
