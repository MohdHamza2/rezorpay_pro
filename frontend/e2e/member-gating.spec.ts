import { expect, test } from '@playwright/test';
import {
  putWorkspaceFtaApi,
  registerWorkspace,
  seedArInvoice,
  seedDbMember,
  workspaceId,
} from './helpers';

test.describe('Reports: MEMBER role gating on VAT and Analytics', () => {
  test('MEMBER sees OWNER/ADMIN notice on VAT and Analytics tabs, no fetch fires', async ({
    request,
    page,
  }) => {
    test.setTimeout(120_000);
    const { token: ownerToken } = await registerWorkspace(request, 'member-gate');
    await putWorkspaceFtaApi(request, ownerToken);
    await seedArInvoice(request, ownerToken, { clientName: 'Member Client' });
    const wsId = await workspaceId(request, ownerToken);
    const memberEmail = await seedDbMember(wsId);
    await page.goto('/login');
    await page.locator('#email').fill(memberEmail);
    await page.locator('#password').fill('Passw0rd1');
    await page.getByRole('button', { name: 'Login' }).click();
    await expect(page.getByTestId('app-layout')).toBeVisible({ timeout: 20_000 });
    // Wait for auth to settle
    await page.waitForTimeout(500);

    const fired: string[] = [];
    page.on('request', (r) => {
      const url = r.url();
      if (url.includes('/api/v1/reports/vat-compliance') || url.includes('/api/v1/reports/analytics')) {
        fired.push(url);
      }
    });

    await page.goto('/reports');
    await page.getByRole('button', { name: /VAT Compliance/ }).click();
    await expect(page.getByText('OWNER/ADMIN only')).toBeVisible({ timeout: 10_000 });
    await page.waitForTimeout(300);
    expect(fired.filter((u) => u.includes('/api/v1/reports/vat-compliance'))).toHaveLength(0);

    await page.getByRole('button', { name: /Analytics/ }).click();
    await expect(page.getByText('OWNER/ADMIN only')).toBeVisible({ timeout: 10_000 });
    await page.waitForTimeout(300);
    expect(fired.filter((u) => u.includes('/api/v1/reports/analytics'))).toHaveLength(0);

    await page.getByRole('button', { name: /AR Aging/ }).click();
    await expect(page.getByTestId('report-ar-total')).toContainText('210.00');
  });
});
