import { expect, test } from '@playwright/test';
import {
  authJson,
  createAdhocLpoViaUi,
  createAdhocQuotationViaUi,
  createClientViaUi,
  pageAccessToken,
  registerViaUi,
  uniqueEmail,
} from './helpers';

test('manual LPO receive partial invoice lands draft invoice', async ({ page }) => {
  test.setTimeout(120_000);
  const { suffix } = await registerViaUi(page, 'lpo');
  const clientName = `LPO buyer ${suffix}`;

  await createClientViaUi(page, {
    name: clientName,
    email: uniqueEmail('lpo-buyer'),
    address: 'Plot 4, Mussafah, Abu Dhabi',
  });
  await createAdhocLpoViaUi(page, {
    clientName,
    description: 'NYA 4mm cable',
    quantity: '2',
    price: '100.00',
  });

  await expect(page.getByTestId('lpo-status')).toContainText('DRAFT');
  await expect(page.getByTestId('lpo-edit')).toBeVisible();
  await expect(page.getByTestId('lpo-number')).toHaveText(/LPO-\d{4}-\d{4}/);

  await page.getByTestId('lpo-preview-pdf').click();
  await expect(page.getByTestId('lpo-pdf-preview')).toBeVisible();
  await expect(page.getByTestId('lpo-pdf-title')).toHaveText('LPO');
  await expect(page.getByTestId('lpo-pdf-title-ar')).toHaveText('أمر شراء محلي');
  await expect(page.getByTestId('lpo-pdf-title')).not.toHaveText('Tax Invoice');
  await expect(page.getByTestId('pdf-title')).toHaveCount(0);
  await page.getByTestId('lpo-pdf-preview-close').click();

  await page.getByTestId('lpo-receive').click();
  await expect(page.getByTestId('lpo-status')).toContainText('RECEIVED');
  await expect(page.getByTestId('lpo-invoice-panel')).toBeVisible();
  await expect(page.getByTestId('lpo-remaining-0')).toHaveText(/^2(\.0+)?$/);

  await page.getByTestId('lpo-invoice-qty-0').fill('1');
  await page.getByTestId('lpo-invoice').click();
  await expect(page).toHaveURL(/\/invoices$/);
  await expect(page.locator('[data-testid^="invoice-row-"]')).toBeVisible();
  await expect(page.getByTestId('invoice-status')).toContainText('DRAFT');

  await page.getByTestId('invoice-send').click();
  await expect(page.getByTestId('fta-send-blocked')).toBeVisible();
  await expect(page.getByTestId('invoice-status')).toContainText('DRAFT');

  await createAdhocQuotationViaUi(page, {
    clientName,
    description: 'NYA 4mm cable LPO convert',
    quantity: '1',
    price: '50.00',
  });
  await page.getByTestId('quotation-send').click();
  await expect(page.getByTestId('quotation-status')).toContainText('SENT');
  await page.getByTestId('quotation-accept').click();
  await expect(page.getByTestId('quotation-status')).toContainText('ACCEPTED');

  const quoteId = page.url().split('/').filter(Boolean).pop() as string;
  await page.getByTestId('quotation-convert-lpo').click();
  await expect(page.getByTestId('lpo-detail')).toBeVisible();
  await expect(page).toHaveURL(/\/lpos\/[0-9a-f-]{36}$/i);
  await expect(page.getByTestId('lpo-status')).toContainText('DRAFT');
  await expect(page.getByTestId('lpo-number')).toHaveText(/LPO-\d{4}-\d{4}/);

  const token = await pageAccessToken(page);
  const blockedConvert = await authJson(
    page.request,
    'POST',
    `/api/v1/quotations/${quoteId}/convert-to-invoice`,
    token,
  );
  expect(blockedConvert.status(), await blockedConvert.text()).toBe(409);
  expect((await blockedConvert.json()).error?.code).toBe('CONFLICT');
});
