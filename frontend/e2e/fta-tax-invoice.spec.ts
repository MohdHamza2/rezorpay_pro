import { expect, test } from '@playwright/test';
import {
  FTA_TRN,
  createAdhocInvoiceViaUi,
  createClientViaUi,
  registerViaUi,
  saveWorkspaceFta,
  uniqueEmail,
} from './helpers';

test('simplified tax invoice send and preview', async ({ page }) => {
  test.setTimeout(120_000);
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
  await expect(page.getByTestId('pdf-seller-trn')).toContainText(FTA_TRN);

  await page.getByTestId('pdf-preview-close').click();
  await page.reload();
  await expect(page.getByTestId('invoice-status')).toContainText('SENT');
});
