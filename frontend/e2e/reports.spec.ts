import { expect, test } from '@playwright/test';
import * as fs from 'fs';
import {
  isoDate,
  putWorkspaceFtaApi,
  recordApPayment,
  recordArPayment,
  registerWorkspace,
  seedApApprovedChain,
  seedArInvoice,
  setAuthToken,
  uniqueSuffix,
} from './helpers';

test.describe('Reports: AR aging, statements, VAT, analytics', () => {
  test('AR aging shows outstanding receivables by bucket', async ({ request, page }) => {
    test.setTimeout(120_000);
    const { token } = await registerWorkspace(request, 'reports-ar');
    await putWorkspaceFtaApi(request, token);
    await setAuthToken(page, token);
    const { clientId } = await seedArInvoice(request, token, { clientName: 'Client Alpha' });
    await page.goto('/reports');
    await expect(page.getByText('AR Aging')).toBeVisible();
    await expect(page.getByTestId('report-ar-total')).toContainText('210.00');
    const row = page.getByTestId(`report-ar-customer-row-${clientId}`);
    await expect(row).toBeVisible();
    await expect(row).toContainText('Client Alpha');
    await expect(row).toContainText('210.00');
  });

  test('historical AR reconstruction recomputes as-of balances', async ({ request, page }) => {
    test.setTimeout(120_000);
    const { token } = await registerWorkspace(request, 'reports-hist');
    await putWorkspaceFtaApi(request, token);
    await setAuthToken(page, token);
    const { clientId, invoiceId } = await seedArInvoice(request, token, {
      clientName: 'Client Hist',
      issueDate: isoDate(-1),
    });
    await recordArPayment(request, token, invoiceId, '60.00');
    await page.goto('/reports');
    await expect(page.getByTestId('report-ar-total')).toContainText('150.00');
    await page.getByLabel('Historical balance reconstruction').check();
    await page.getByLabel('As of').fill(isoDate(-1));
    await expect(page.getByTestId('report-ar-total')).toContainText('210.00');
  });

  test('AR statement CSV and PDF exports', async ({ request, page }) => {
    test.setTimeout(120_000);
    const { token } = await registerWorkspace(request, 'reports-stmt');
    await putWorkspaceFtaApi(request, token);
    await setAuthToken(page, token);
    const { clientId } = await seedArInvoice(request, token, { clientName: 'Client Stmt' });
    await page.goto('/reports');
    const row = page.getByTestId(`report-ar-customer-row-${clientId}`);
    const today = isoDate();
    const monthStart = `${today.slice(0, 7)}-01`;

    async function downloadStatement(fmt: 'csv' | 'pdf') {
      await row.getByRole('button', { name: 'Statement', exact: true }).click();
      const dl = page.waitForEvent('download');
      await row.getByRole('button', { name: fmt === 'csv' ? 'Statement CSV' : 'Statement PDF' }).click();
      const download = await dl;
      expect(download.suggestedFilename()).toBe(
        `ar-statement-${clientId}-${monthStart}_to_${today}.${fmt}`
      );
      return download;
    }

    const csv = await downloadStatement('csv');
    const csvPath = await csv.path();
    expect(csvPath).toBeTruthy();
    const csvContent = fs.readFileSync(csvPath!, 'utf8');
    expect(csvContent).toContain('Entity Name');
    expect(csvContent).toContain('Client Stmt');

    const pdf = await downloadStatement('pdf');
    const pdfPath = await pdf.path();
    expect(pdfPath).toBeTruthy();
    const pdfBytes = fs.readFileSync(pdfPath!);
    expect(pdfBytes.slice(0, 4).toString()).toBe('%PDF');
  });

  test('AP aging tracks supplier invoices and partial payment', async ({ request, page }) => {
    test.setTimeout(180_000);
    const { token } = await registerWorkspace(request, 'reports-ap');
    await putWorkspaceFtaApi(request, token);
    await setAuthToken(page, token);
    const suffix = uniqueSuffix();
    const { supplierId, invoiceId } = await seedApApprovedChain(request, token, suffix, 'Supplier Beta');
    await page.goto('/reports');
    await page.getByRole('button', { name: /AP Aging/ }).click();
    await expect(page.getByTestId('report-ap-total')).toContainText('300.00');
    await recordApPayment(request, token, invoiceId, '100.00');
    await page.goto('/reports');
    await page.getByRole('button', { name: /AP Aging/ }).click();
    await expect(page.getByTestId('report-ap-total')).toContainText('200.00');
    const sRow = page.getByTestId(`report-ap-supplier-row-${supplierId}`);
    await expect(sRow).toContainText('200.00');
  });

  test('VAT compliance preview shows deterministic manifest', async ({ request, page }) => {
    test.setTimeout(120_000);
    const { token } = await registerWorkspace(request, 'reports-vat');
    await putWorkspaceFtaApi(request, token);
    await setAuthToken(page, token);
    await seedArInvoice(request, token, { clientName: 'Client Vat' });
    await page.goto('/reports');
    await page.getByRole('button', { name: /VAT Compliance/ }).click();
    const today = isoDate();
    const from = `${today.slice(0, 7)}-01`;
    await page.getByLabel('From').fill(from);
    await page.getByLabel('To').fill(today);
    await page.getByRole('button', { name: /Preview JSON/ }).click();
    const preview = page.getByTestId('report-vat-preview');
    await expect(preview).toBeVisible();
    await expect(preview).toContainText('"sales_invoices": 1');
    await expect(preview).toContainText('"output_tax": "10.00"');
    await expect(preview).toContainText('"input_tax": "0.00"');
    await expect(preview).toContainText('"net_tax": "10.00"');
  });

  test('Analytics revenue and tables match seeded invoice amounts', async ({ request, page }) => {
    test.setTimeout(120_000);
    const { token } = await registerWorkspace(request, 'reports-analytics');
    await putWorkspaceFtaApi(request, token);
    await setAuthToken(page, token);
    await seedArInvoice(request, token, { clientName: 'Client Analytics' });
    await page.goto('/reports');
    await page.getByRole('button', { name: /Analytics/ }).click();
    await expect(page.getByRole('heading', { name: /Revenue/ })).toBeVisible();
    await expect(page.locator('td').filter({ hasText: /210\.00/ }).first()).toBeVisible({ timeout: 30000 });
    await expect(page.locator('td').filter({ hasText: /210\.00/ }).nth(1)).toBeVisible({ timeout: 30000 });
  });
});
