import {test,expect} from '@playwright/test';
test('sign in is accessible at desktop and mobile sizes', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route('**/api/v1/auth/me', route => route.fulfill({
    status: 401, json: { detail: 'Not authenticated' },
    headers: { 'access-control-allow-origin': route.request().headers().origin ?? 'http://localhost:3000', 'access-control-allow-credentials': 'true' },
  }));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Sign in to Aster' })).toBeVisible();
  await expect(page.getByLabel('Email address')).toBeVisible();
  await page.screenshot({ path: 'test-results/aster-sign-in.png' });
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByRole('button', { name: 'Explore demo workspace' })).toBeVisible();
  await expect(page.getByText('Example workspace')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/aster-mobile-sign-in.png', fullPage: true });
});

test('workspace navigation and inline sources work at desktop and phone sizes', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const origin = route.request().headers().origin ?? 'http://localhost:3000';
    const headers = { 'access-control-allow-origin': origin, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'x-csrf-token, content-type' };
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    if (path.endsWith('/auth/me')) return route.fulfill({ headers, json: {
      id: 'demo', name: 'Demo visitor', email: 'demo@example.test', role: 'demo', organization_id: 'org', workspace_id: 'workspace', csrf_token: 'e2e-csrf',
    } });
    if (path.endsWith('/chat/stream')) {
      const result = {
        session_id: 'session-1', message_id: 'message-1', status: 'answered',
        answer: 'Read the leave policy for the approval steps. [chunk-1]',
        citations: [{ id: 'chunk-1', document_id: 'leave-policy', title: 'Leave policy', text: 'Example approval steps.', page: 2 }],
      };
      return route.fulfill({ headers, contentType: 'text/event-stream', body: `event: result\ndata: ${JSON.stringify(result)}\n\nevent: done\ndata: {}\n\n` });
    }
    return route.fulfill({ headers, json: [] });
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'What would you like to find?' })).toBeVisible();
  await page.screenshot({ path: 'test-results/aster-desktop.png' });
  await page.getByRole('button', { name: 'What is the organization’s leave policy?' }).click();
  await expect(page.getByRole('textbox', { name: 'Ask a question' })).toBeFocused();
  await page.getByRole('button', { name: 'Send question' }).click();
  const citation = page.getByRole('button', { name: 'Inspect source 1' });
  await expect(citation).toBeVisible();
  await citation.click();
  await expect(page.getByRole('complementary', { name: 'Answer sources' }).getByText('Example approval steps.')).toBeVisible();

  await page.setViewportSize({ width: 375, height: 812 });
  await citation.click();
  const drawer = page.getByRole('dialog', { name: 'Answer sources' });
  await expect(drawer.getByText('Example approval steps.')).toBeVisible();
  await page.screenshot({ path: 'test-results/aster-mobile-sources.png' });
  await page.keyboard.press('Escape');
  await expect(drawer).toBeHidden();
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await expect(page.getByRole('dialog', { name: 'Workspace navigation' })).toBeVisible();
  await page.getByRole('link', { name: 'Knowledge library' }).click();
  await expect(page.getByRole('heading', { name: 'Workspace documents' })).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Workspace navigation' })).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
