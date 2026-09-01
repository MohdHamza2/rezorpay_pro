import { expect, test } from '@playwright/test';
import {
  API_URL,
  authJson,
  createAdhocQuotationViaUi,
  createClientViaUi,
  pageAccessToken,
  registerViaUi,
  uniqueEmail,
} from './helpers';

test('quotation send accept convert to draft invoice', async ({ page }) => {
  test.setTimeout(120_000);
  const { suffix } = await registerViaUi(page, 'quo');
  const clientName = `Quote buyer ${suffix}`;

  await createClientViaUi(page, {
    name: clientName,
    email: uniqueEmail('quo-buyer'),
    address: 'Plot 4, Mussafah, Abu Dhabi',
  });
  await createAdhocQuotationViaUi(page, {
    clientName,
    description: 'NYA 4mm cable',
    quantity: '2',
    price: '100.00',
  });

  await expect(page.getByTestId('quotation-status')).toContainText('DRAFT');
  await expect(page.getByTestId('quotation-edit')).toBeVisible();
  await expect(page.getByTestId('quotation-number')).toHaveText(/QUO-\d{4}-\d{4}/);

  await page.getByTestId('quotation-preview-pdf').click();
  await expect(page.getByTestId('quotation-pdf-preview')).toBeVisible();
  await expect(page.getByTestId('quotation-pdf-title')).toHaveText('Quotation');
  await expect(page.getByTestId('quotation-pdf-title-ar')).toHaveText('عرض سعر');
  await expect(page.getByTestId('quotation-pdf-title')).not.toHaveText('Tax Invoice');
  await expect(page.getByTestId('pdf-title')).toHaveCount(0);
  await page.getByTestId('quotation-pdf-preview-close').click();

  await page.getByTestId('quotation-send').click();
  await expect(page.getByTestId('quotation-status')).toContainText('SENT');
  await expect(page.getByTestId('quotation-edit')).toHaveCount(0);

  const quoteId = page.url().split('/').filter(Boolean).pop() as string;
  const token = await pageAccessToken(page);
  const blockedPut = await authJson(page.request, 'PUT', `/api/v1/quotations/${quoteId}`, token, {
    notes: 'should not save on SENT',
  });
  expect(blockedPut.status(), await blockedPut.text()).toBe(403);
  expect((await blockedPut.json()).error?.code).toBe('INVALID_STATE');

  await page.goto(`/quotations/${quoteId}/edit`);
  await expect(page.getByTestId('quotation-detail')).toBeVisible();
  await expect(page.getByTestId('quotation-status')).toContainText('SENT');
  await expect(page).toHaveURL(new RegExp(`/quotations/${quoteId}$`));

  await page.getByTestId('quotation-accept').click();
  await expect(page.getByTestId('quotation-status')).toContainText('ACCEPTED');

  await page.getByTestId('quotation-convert').click();
  await expect(page).toHaveURL(/\/invoices$/);
  await expect(page.locator('[data-testid^="invoice-row-"]')).toBeVisible();
  await expect(page.getByTestId('invoice-status')).toContainText('DRAFT');

  await page.getByTestId('invoice-send').click();
  await expect(page.getByTestId('fta-send-blocked')).toBeVisible();
  await expect(page.getByTestId('invoice-status')).toContainText('DRAFT');
});
