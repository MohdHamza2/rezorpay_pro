import { expect, test } from '@playwright/test';
import {
  isoDate,
  putWorkspaceFtaApi,
  registerWorkspace,
  seedApApprovedChain,
  seedArInvoice,
  setAuthToken,
  uniqueSuffix,
} from './helpers';

test.describe('Reports isolation: cross-tenant data separation', () => {
  test('workspace B cannot see workspace A AR/AP data', async ({ request, page }) => {
    test.setTimeout(180_000);

    const wsA = await registerWorkspace(request, 'iso-a');
    await putWorkspaceFtaApi(request, wsA.token);
    const aSuffix = uniqueSuffix();
    const aAr = await seedArInvoice(request, wsA.token, { clientName: 'Client A', issueDate: isoDate() });
    const aAp = await seedApApprovedChain(request, wsA.token, aSuffix, 'Supplier A');

    const wsB = await registerWorkspace(request, 'iso-b');
    await putWorkspaceFtaApi(request, wsB.token);
    const bSuffix = uniqueSuffix();
    const bAr = await seedArInvoice(request, wsB.token, { clientName: 'Client B', issueDate: isoDate() });
    const bAp = await seedApApprovedChain(request, wsB.token, bSuffix, 'Supplier B');

    await setAuthToken(page, wsB.token);
    await page.goto('/reports');
    await expect(page.getByText('AR Aging')).toBeVisible();
    await expect(page.getByTestId('report-ar-total')).toContainText('210.00');
    await expect(page.getByTestId(`report-ar-customer-row-${bAr.clientId}`)).toBeVisible();
    await expect(page.getByTestId(`report-ar-customer-row-${bAr.clientId}`)).toContainText('Client B');
    await expect(page.getByTestId(`report-ar-customer-row-${aAr.clientId}`)).toHaveCount(0);

    await page.getByRole('button', { name: /AP Aging/ }).click();
    await expect(page.getByTestId('report-ap-total')).toContainText('300.00');
    await expect(page.getByTestId(`report-ap-supplier-row-${bAp.supplierId}`)).toBeVisible();
    await expect(page.getByTestId(`report-ap-supplier-row-${bAp.supplierId}`)).toContainText('Supplier B');
    await expect(page.getByTestId(`report-ap-supplier-row-${aAp.supplierId}`)).toHaveCount(0);
  });
});
