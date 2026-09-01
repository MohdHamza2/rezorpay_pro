import { expect, test, type Locator, type Page } from '@playwright/test';
import {
  createAdhocInvoiceViaUi,
  createClientViaUi,
  isoDate,
  registerViaUi,
  saveWorkspaceFta,
  uniqueEmail,
} from './helpers';

async function recordCashPaymentViaUi(page: Page, amount: string): Promise<void> {
  await page.getByTitle('Record Payment').click();
  const heading = page.getByRole('heading', { name: 'Record Payment' });
  await expect(heading).toBeVisible();
  const modal = page
    .locator('div')
    .filter({ has: heading })
    .filter({ has: page.getByRole('button', { name: 'Record Payment' }) })
    .last();
  await modal.locator('input[type="number"]').fill(amount);
  await modal.locator('select').selectOption('CASH');
  await modal.getByRole('button', { name: 'Record Payment' }).click();
  await expect(heading).toHaveCount(0);
}

async function applyStatementRange(page: Page): Promise<void> {
  const today = isoDate();
  await page.getByTestId('statement-from').fill(today);
  await page.getByTestId('statement-to').fill(today);
  await page.getByTestId('statement-as-of').fill(today);
  await page.getByTestId('statement-apply').click();
}

async function expectAccountStatementTitle(locator: Locator): Promise<void> {
  await expect(locator).toHaveText('Account Statement');
  await expect(locator).not.toHaveText(/Tax Invoice|Tax Credit Note|^INVOICE$/);
}

test('account statement shows invoice payment and credit note', async ({ page }) => {
  test.setTimeout(120_000);
  const { suffix } = await registerViaUi(page, 'ar-stmt');
  const clientName = `AR buyer ${suffix}`;

  await saveWorkspaceFta(page);
  await createClientViaUi(page, {
    name: clientName,
    email: uniqueEmail('ar-buyer'),
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

  await recordCashPaymentViaUi(page, '50.00');
  await expect(page.getByTestId('invoice-status')).toContainText('PARTIALLY PAID');
  await expect(page.getByTestId('invoice-amount-paid')).toHaveText('AED 50.00');

  await page.getByTestId('invoice-create-cn').click();
  await expect(page.getByTestId('cn-form')).toBeVisible();
  await page.getByTestId('cn-qty-0').fill('1');
  await page.getByTestId('cn-form-submit').click();
  await expect(page.getByTestId('cn-detail')).toBeVisible();
  await page.getByTestId('cn-issue').click();
  await expect(page.getByTestId('cn-status')).toContainText('ISSUED');

  await page.getByTestId('nav-clients').click();
  await page.getByTestId(`client-row-${clientName}`).getByTestId('client-statement').click();
  await expect(page.getByTestId('ar-statement')).toBeVisible();
  await applyStatementRange(page);
  await expect(page.getByTestId('statement-lines')).toBeVisible();

  const pageTitle = page.locator('h2[data-testid="statement-pdf-title"]');
  await expectAccountStatementTitle(pageTitle);
  await expect(page.getByTestId('pdf-title')).toHaveCount(0);
  await expect(page.getByTestId('cn-pdf-title')).toHaveCount(0);

  await expect(page.getByTestId('statement-line-TAX_INVOICE')).toContainText('Tax Invoice');
  await expect(page.getByTestId('statement-line-PAYMENT')).toContainText('Payment');
  await expect(page.getByTestId('statement-line-TAX_CREDIT_NOTE')).toContainText('Tax Credit Note');
  await expect(page.getByTestId('statement-line-PAYMENT')).not.toContainText('Tax Credit Note');
  await expect(page.getByTestId('statement-line-TAX_CREDIT_NOTE')).not.toContainText('Payment');

  await expect(page.getByTestId('statement-paid')).toHaveText('AED 50.00');
  await expect(page.getByTestId('statement-credited')).toHaveText('AED 105.00');
  const paid = await page.getByTestId('statement-paid').innerText();
  const credited = await page.getByTestId('statement-credited').innerText();
  expect(credited).not.toEqual(paid);

  await expect(page.getByTestId('statement-amount-due')).toBeVisible();
  await expect(page.getByTestId('statement-unapplied')).toBeVisible();
  await expect(page.getByTestId('statement-aging')).toBeVisible();

  await page.getByTestId('statement-preview-pdf').click();
  const preview = page.getByTestId('statement-pdf-preview');
  await expect(preview).toBeVisible();
  await expectAccountStatementTitle(preview.getByTestId('statement-pdf-title'));
});
