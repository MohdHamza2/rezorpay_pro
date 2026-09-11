import { expect, test } from '@playwright/test';
import {
  putWorkspaceFtaApi,
  registerWorkspace,
  seedApApprovedChain,
  seedArInvoice,
  setAuthToken,
  uniqueSuffix,
} from './helpers';

test.describe('Dashboard: stats, recent invoices, quick actions', () => {
  test('empty state shows zeros and no invoices', async ({ request, page }) => {
    test.setTimeout(60_000);
    const { token } = await registerWorkspace(request, 'dash-empty');
    await setAuthToken(page, token);
    await page.goto('/');
    await expect(page.getByTestId('dash-total-receivables')).toContainText('AED 0');
    await expect(page.getByText('No invoices yet')).toBeVisible();
    await expect(page.getByTestId('dash-ar-snapshot')).toContainText('AED 0');
    await expect(page.getByTestId('dash-ap-snapshot')).toContainText('AED 0');
  });

test('populated dashboard reflects AR/AP invoices and links navigate correctly', async ({ request, page }) => {
    test.setTimeout(120_000);
    const { token } = await registerWorkspace(request, 'dash-pop');
    await putWorkspaceFtaApi(request, token);
    await setAuthToken(page, token);
    const { clientId, invoiceId } = await seedArInvoice(request, token, { clientName: 'Dash Client' });
    const { invoiceId: apInvoiceId, supplierId } = await seedApApprovedChain(
      request,
      token,
      uniqueSuffix(),
      'Dash Supplier'
    );

    // Debug: check dashboard stats API directly
    const statsResp = await request.get('http://127.0.0.1:8000/api/v1/dashboard/stats', {
      headers: { Authorization: `Bearer ${token}` }
    });
    console.log('[DEBUG] Dashboard stats API:', await statsResp.json());

    // Debug: check AR aging summary API directly
    const arResp = await request.get('http://127.0.0.1:8000/api/v1/ar-aging', {
      headers: { Authorization: `Bearer ${token}` }
    });
    console.log('[DEBUG] AR Aging summary API:', await arResp.json());

    await page.goto('/');
    await expect(page.getByTestId('dash-total-receivables')).toContainText('210.00');
    await expect(page.getByTestId('dash-recent-invoices')).toContainText('INV-');
    await expect(page.getByTestId('dash-recent-invoices')).toContainText('210.00');
    await expect(page.getByTestId('dash-ar-snapshot')).toContainText('210.00');
    await expect(page.getByTestId('dash-ap-snapshot')).toContainText('300.00');

    const createInvoiceLink = page.getByRole('link', { name: /Create Invoice/ });
    await expect(createInvoiceLink).toHaveAttribute('href', '/invoices?new=1');
    await createInvoiceLink.click();
    await expect(page.getByRole('heading', { name: 'Create Invoice' })).toBeVisible();
    await page.goto('/');

const procurementLink = page.getByRole('link', { name: /Log Procurement Request/ });
    await expect(procurementLink).toHaveAttribute('href', '/procurement');
    await procurementLink.click();
    await expect(page.getByRole('heading', { name: 'Internal Procurement' })).toBeVisible({ timeout: 20_000 });
    await page.goto('/');

const grnLink = page.getByRole('link', { name: /Record Goods Receipt/ });
    await expect(grnLink).toHaveAttribute('href', '/grn');
    await grnLink.click();
    await expect(page.getByRole('heading', { name: 'Inbound Shipments (GRN)' })).toBeVisible({ timeout: 20_000 });
    await page.goto('/');
  });

  test('AR/AP snapshot links navigate to Reports with correct tab', async ({ request, page }) => {
    test.setTimeout(120_000);
    const { token } = await registerWorkspace(request, 'dash-snap');
    await putWorkspaceFtaApi(request, token);
    await setAuthToken(page, token);
    await seedArInvoice(request, token, { clientName: 'Snap Client' });
    await seedApApprovedChain(request, token, uniqueSuffix(), 'Snap Supplier');
    await page.goto('/');
    await page.getByRole('link', { name: /AR \(receivables\)/ }).click();
    await expect(page.getByText('AR Aging')).toBeVisible();
    await expect(page.getByTestId('report-ar-total')).toContainText('210.00');
    await page.goto('/');
    await page.getByRole('link', { name: /AP \(payables\)/ }).click();
    await page.getByRole('button', { name: /AP Aging/ }).click();
    await expect(page.getByTestId('report-ap-total')).toContainText('300.00');
  });
});
