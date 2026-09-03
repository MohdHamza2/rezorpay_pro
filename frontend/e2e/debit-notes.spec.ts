import { expect, test } from '@playwright/test';
import {
  FTA_TRN,
  createAdhocInvoiceViaUi,
  createClientViaUi,
  registerViaUi,
  saveWorkspaceFta,
  uniqueEmail,
} from './helpers';

test('simplified tax invoice debit note issue posts AR and increases balance due', async ({ page }) => {
  test.setTimeout(120_000);
  const { suffix } = await registerViaUi(page, 'tdn');
  const clientName = `TDN buyer ${suffix}`;

  await saveWorkspaceFta(page);
  await createClientViaUi(page, {
    name: clientName,
    email: uniqueEmail('tdn-buyer'),
    address: 'Plot 5, Mussafah, Abu Dhabi',
  });
  await createAdhocInvoiceViaUi(page, {
    clientName,
    description: 'NYA 4mm cable',
    quantity: '2',
    price: '100.00',
  });

  await expect(page.getByTestId('invoice-status')).toContainText('DRAFT');
  await page.getByTestId('invoice-send').click();
  await expect(page.getByTestId('invoice-status')).toContainText('SENT');

  const invoiceRow = page.locator('[data-testid^="invoice-row-"]');
  await expect(invoiceRow.getByTestId('invoice-amount-paid')).toHaveText('AED 0.00');
  await expect(invoiceRow.getByTestId('invoice-balance-due')).toHaveText('AED 210.00');

  await page.getByTestId('invoice-create-tdn').click();
  await expect(page.getByTestId('tdn-form')).toBeVisible();
  
  // Tax Debit Notes don't have a remaining cap. We just set a quantity to increase the consideration.
  await page.getByTestId('tdn-qty-0').waitFor({ timeout: 5000 });
  await page.getByTestId('tdn-qty-0').fill('1');
  await page.getByTestId('tdn-form-submit').click();
  
  await expect(page.getByTestId('tdn-detail')).toBeVisible();
  await expect(page.getByTestId('tdn-status')).toContainText('DRAFT');
  await expect(page.getByTestId('tdn-number')).toHaveText(/TDN-\d{4}-\d{4}/);

  await page.getByTestId('tdn-issue').click();
  await expect(page.getByTestId('tdn-status')).toContainText('ISSUED');

  await page.getByTestId('tdn-preview-pdf').click();
  await expect(page.getByTestId('tdn-pdf-preview')).toBeVisible();
  await expect(page.getByTestId('tdn-pdf-title')).toHaveText('Tax Debit Note');
  await expect(page.getByTestId('tdn-pdf-title-ar')).toHaveText('إشعار مدين ضريبي');
  await expect(page.getByTestId('tdn-pdf-title')).not.toHaveText('Tax Invoice');
  await expect(page.getByTestId('pdf-title')).toHaveCount(0);
  await expect(page.getByTestId('tdn-pdf-seller-trn')).toContainText(FTA_TRN);
  await page.getByTestId('tdn-pdf-preview-close').click();

  await page.getByTestId('nav-invoices').click();
  await expect(invoiceRow.getByTestId('invoice-status')).toContainText('SENT');
  await expect(invoiceRow.getByTestId('invoice-amount-paid')).toHaveText('AED 0.00');
  await expect(invoiceRow.getByTestId('invoice-balance-due')).toHaveText('AED 315.00'); // 210 + 105

  await page.locator('[data-testid^="invoice-open-"]').click();
  const ar = page.getByTestId('invoice-ar-panel');
  await expect(ar).toBeVisible();
  await expect(ar.getByTestId('invoice-amount-paid')).toHaveText('AED 0.00');
  await expect(ar.getByTestId('invoice-amount-debited')).toHaveText('AED 105.00');
  await expect(ar.getByTestId('invoice-balance-due')).toHaveText('AED 315.00');
  
  // AR Statement check
  await page.getByTestId('invoice-ar-close').click();
  await page.getByTestId('nav-clients').click();
  // Find the row for this client and click its statement link
  const clientRow = page.locator('tr', { hasText: clientName });
  await clientRow.getByTestId('client-statement').click();
  await expect(page.getByTestId('statement-debited')).toHaveText('AED 105.00', { timeout: 5000 });
  const stmtRow = page.getByTestId('statement-line-TAX_DEBIT_NOTE').first();
  await expect(stmtRow).toBeVisible();
});
