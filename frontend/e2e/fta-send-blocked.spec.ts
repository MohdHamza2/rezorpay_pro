import { expect, test } from '@playwright/test';
import { createAdhocInvoiceViaUi, createClientViaUi, registerViaUi, uniqueEmail } from './helpers';

test('send invoice without workspace TRN is blocked', async ({ page }) => {
  test.setTimeout(120_000);
  const { suffix } = await registerViaUi(page, 'fta-block');
  const clientName = `Cash ${suffix}`;

  await createClientViaUi(page, {
    name: clientName,
    email: uniqueEmail('buyer-block'),
    address: 'Plot 4, Mussafah, Abu Dhabi',
  });
  await createAdhocInvoiceViaUi(page, {
    clientName,
    description: 'Site cutting charge',
    quantity: '1',
    price: '50.00',
  });

  await expect(page.getByTestId('invoice-status')).toContainText('DRAFT');
  await page.getByTestId('invoice-send').click();
  await expect(page.getByTestId('fta-send-blocked')).toBeVisible();
  await expect(page.getByTestId('fta-send-blocked')).toContainText(/TRN|address/i);
  await expect(page.getByTestId('invoice-status')).toContainText('DRAFT');
});
