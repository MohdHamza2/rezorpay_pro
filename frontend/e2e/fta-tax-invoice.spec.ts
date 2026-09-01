import { expect, test, type Page } from '@playwright/test';
import {
  FTA_TRN,
  createAdhocInvoiceViaUi,
  createClientViaUi,
  registerViaUi,
  saveWorkspaceFta,
  uniqueEmail,
} from './helpers';

function isGoogleFontUrl(url: string): boolean {
  return url.includes('fonts.googleapis.com') || url.includes('fonts.gstatic.com');
}

function watchGoogleFontRequests(page: Page): { urls: string[]; stop: () => void } {
  const urls: string[] = [];
  const onRequest = (request: { url: () => string }) => {
    const url = request.url();
    if (isGoogleFontUrl(url)) urls.push(url);
  };
  page.on('request', onRequest);
  return { urls, stop: () => page.off('request', onRequest) };
}

test('simplified tax invoice send and preview', async ({ page }) => {
  test.setTimeout(120_000);
  const fontWatch = watchGoogleFontRequests(page);
  const { suffix } = await registerViaUi(page, 'fta-ok');
  const clientName = `Buyer ${suffix}`;

  await saveWorkspaceFta(page);
  await createClientViaUi(page, {
    name: clientName,
    email: uniqueEmail('buyer-fta'),
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
  const arTitle = page.getByTestId('pdf-title-ar');
  await expect(arTitle).toHaveText('فاتورة ضريبية');
  await expect(arTitle).toHaveCSS('font-family', /NotoNaskhArabic/);
  await expect(page.getByTestId('pdf-seller-trn')).toContainText(FTA_TRN);
  expect(fontWatch.urls, fontWatch.urls.join('\n')).toEqual([]);
  fontWatch.stop();

  await page.getByTestId('pdf-preview-close').click();
  await page.reload();
  await expect(page.getByTestId('invoice-status')).toContainText('SENT');
});
