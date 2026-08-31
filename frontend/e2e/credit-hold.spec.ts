import { expect, test } from '@playwright/test';
import {
  createAdhocInvoiceViaUi,
  createAdhocLpoViaUi,
  createClientViaUi,
  draftInvoiceRow,
  registerViaUi,
  saveWorkspaceFta,
  uniqueEmail,
} from './helpers';

test('COD client second invoice send is credit HOLD', async ({ page }) => {
  test.setTimeout(120_000);
  const { suffix } = await registerViaUi(page, 'credit-hold');
  const clientName = `COD ${suffix}`;

  await saveWorkspaceFta(page, {
    limitDefault: '0',
    holdDays: '90',
    blockPoOnHold: true,
  });
  await createClientViaUi(page, {
    name: clientName,
    email: uniqueEmail('cod-buyer'),
    address: 'Plot 4, Mussafah, Abu Dhabi',
    creditLimit: '0',
  });
  await createAdhocInvoiceViaUi(page, {
    clientName,
    description: 'NYA 4mm cable',
    quantity: '1',
    price: '100.00',
  });

  await expect(page.getByTestId('invoice-status')).toContainText('DRAFT');
  await page.getByTestId('invoice-send').click();
  await expect(page.getByTestId('invoice-status')).toContainText('SENT');
  await expect(page.getByTestId('fta-send-blocked')).toHaveCount(0);
  await expect(page.getByTestId('credit-hold')).toHaveCount(0);

  await page.getByTestId('nav-clients').click();
  await expect(page.getByTestId(`client-row-${clientName}`)).toBeVisible();
  await expect(page.getByTestId('client-credit-status')).toContainText('HOLD');

  await createAdhocInvoiceViaUi(page, {
    clientName,
    description: 'Second COD invoice',
    quantity: '1',
    price: '25.00',
  });
  const draft = draftInvoiceRow(page);
  await expect(draft.getByTestId('invoice-status')).toContainText('DRAFT');
  await page.getByTestId('invoice-send').click();
  await expect(page.getByTestId('credit-hold')).toBeVisible();
  await expect(page.getByTestId('credit-hold')).toContainText(/credit HOLD/i);
  await expect(page.getByTestId('fta-send-blocked')).toHaveCount(0);
  await expect(draft.getByTestId('invoice-status')).toContainText('DRAFT');

  await createAdhocLpoViaUi(page, {
    clientName,
    description: 'HOLD LPO line',
    quantity: '1',
    price: '40.00',
  });
  await expect(page.getByTestId('lpo-status')).toContainText('DRAFT');
  await page.getByTestId('lpo-receive').click();
  await expect(page.getByTestId('credit-hold')).toBeVisible();
  await expect(page.getByTestId('credit-hold')).toContainText(/credit HOLD/i);
  await expect(page.getByTestId('lpo-status')).toContainText('DRAFT');
});
