import { expect, test } from '@playwright/test';
import {
  FTA_TRN,
  createAdhocInvoiceViaUi,
  createClientViaUi,
  registerViaUi,
  saveWorkspaceFta,
  uniqueEmail,
} from './helpers';

test('simplified tax invoice credit note issue posts AR', async ({ page }) => {
  test.setTimeout(120_000);
  const { suffix } = await registerViaUi(page, 'cn');
  const clientName = `CN buyer ${suffix}`;

  await saveWorkspaceFta(page);
  await createClientViaUi(page, {
    name: clientName,
    email: uniqueEmail('cn-buyer'),
    address: 'Plot 4, Mussafah, Abu Dhabi',
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
  await expect(page.getByTestId('fta-send-blocked')).toHaveCount(0);

  await page.getByTestId('invoice-preview-pdf').click();
  await expect(page.getByTestId('pdf-preview')).toBeVisible();
  await expect(page.getByTestId('pdf-title')).toHaveText('Tax Invoice');
  await page.getByTestId('pdf-preview-close').click();

  const invoiceRow = page.locator('[data-testid^="invoice-row-"]');
  await expect(invoiceRow.getByTestId('invoice-amount-paid')).toHaveText('AED 0.00');
  await expect(invoiceRow.getByTestId('invoice-balance-due')).toHaveText('AED 210.00');

  await page.getByTestId('invoice-create-cn').click();
  await expect(page.getByTestId('cn-form')).toBeVisible();
  await expect(page.getByTestId('cn-remaining-0')).toHaveText(/^2(\.0+)?$/);
  await expect(page.getByTestId('cn-qty-0')).toHaveValue(/^2(\.0+)?$/);

  await page.getByTestId('cn-qty-0').fill('99');
  await page.getByTestId('cn-form-submit').click();
  await expect(page.getByTestId('cn-qty-error-0')).toContainText(/Cannot exceed remaining/i);
  await expect(page.getByTestId('cn-detail')).toHaveCount(0);

  await page.getByTestId('cn-qty-0').fill('1');
  await page.getByTestId('cn-form-submit').click();
  await expect(page.getByTestId('cn-detail')).toBeVisible();
  await expect(page.getByTestId('cn-status')).toContainText('DRAFT');
  await expect(page.getByTestId('cn-number')).toHaveText(/CN-\d{4}-\d{4}/);

  await page.getByTestId('cn-issue').click();
  await expect(page.getByTestId('cn-status')).toContainText('ISSUED');

  await page.getByTestId('cn-preview-pdf').click();
  await expect(page.getByTestId('cn-pdf-preview')).toBeVisible();
  await expect(page.getByTestId('cn-pdf-title')).toHaveText('Tax Credit Note');
  await expect(page.getByTestId('cn-pdf-title')).not.toHaveText('Tax Invoice');
  await expect(page.getByTestId('pdf-title')).toHaveCount(0);
  await expect(page.getByTestId('cn-pdf-seller-trn')).toContainText(FTA_TRN);
  await page.getByTestId('cn-pdf-preview-close').click();

  await page.getByTestId('nav-invoices').click();
  await expect(invoiceRow.getByTestId('invoice-status')).toContainText('SENT');
  await expect(invoiceRow.getByTestId('invoice-amount-paid')).toHaveText('AED 0.00');
  await expect(invoiceRow.getByTestId('invoice-balance-due')).toHaveText('AED 105.00');

  await page.locator('[data-testid^="invoice-open-"]').click();
  const ar = page.getByTestId('invoice-ar-panel');
  await expect(ar).toBeVisible();
  await expect(ar.getByTestId('invoice-amount-paid')).toHaveText('AED 0.00');
  await expect(ar.getByTestId('invoice-amount-credited')).toHaveText('AED 105.00');
  await expect(ar.getByTestId('invoice-balance-due')).toHaveText('AED 105.00');
  await expect(ar).toContainText('not cash payments');
  await expect(ar).toContainText('Amount paid (cash)');
  await expect(ar).toContainText('Amount credited (credit notes)');
});
