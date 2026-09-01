import { expect, test, type Page } from '@playwright/test';
import {
  authJson,
  createAdhocInvoiceViaUi,
  createClientViaUi,
  expectApiData,
  isoDate,
  pageAccessToken,
  registerViaUi,
  saveWorkspaceFta,
  uniqueEmail,
} from './helpers';

async function registerFtaClient(page: Page, prefix: string): Promise<string> {
  const { suffix } = await registerViaUi(page, prefix);
  const clientName = `PDC buyer ${suffix}`;
  await saveWorkspaceFta(page);
  await createClientViaUi(page, {
    name: clientName,
    email: uniqueEmail('pdc-buyer'),
    address: 'Plot 4, Mussafah, Abu Dhabi',
  });
  return clientName;
}

async function createAndSendInvoice(page: Page, clientName: string): Promise<void> {
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
}

function invoiceRow(page: Page) {
  return page.locator('[data-testid^="invoice-row-"]');
}

async function recordPdc(page: Page, pdcDate: string): Promise<void> {
  await page.getByTestId('invoice-record-payment').click();
  await expect(page.getByTestId('payment-submit')).toBeVisible();
  await page.getByTestId('payment-method').selectOption('PDC');
  await page.getByTestId('payment-pdc-date').fill(pdcDate);
  await page.getByTestId('payment-submit').click();
  await expect(page.getByTestId('payment-submit')).toHaveCount(0);
}

async function openPaymentList(page: Page) {
  await page.locator('[data-testid^="invoice-open-"]').click();
  const panel = page.getByTestId('invoice-ar-panel');
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId('payment-list')).toBeVisible();
  return panel;
}

test('future PDC stays SENT and is not cash', async ({ page }) => {
  test.setTimeout(120_000);
  const clientName = await registerFtaClient(page, 'pdc-future');
  await createAndSendInvoice(page, clientName);

  const row = invoiceRow(page);
  await expect(row.getByTestId('invoice-amount-paid')).toHaveText('AED 0.00');
  await expect(row.getByTestId('invoice-balance-due')).toHaveText('AED 210.00');

  await recordPdc(page, isoDate(7));
  await expect(row.getByTestId('invoice-status')).toContainText('SENT');
  await expect(row.getByTestId('invoice-status')).not.toContainText('PAID');
  await expect(row.getByTestId('invoice-amount-paid')).toHaveText('AED 0.00');
  await expect(row.getByTestId('invoice-balance-due')).toHaveText('AED 210.00');

  const panel = await openPaymentList(page);
  const payRow = panel.locator('[data-testid^="payment-row-"]');
  await expect(payRow).toBeVisible();
  await expect(payRow).toContainText('PDC');
  await expect(payRow).toContainText('PENDING');
  await expect(payRow).toContainText('not cash');
  await expect(payRow).toContainText('RECEIVED');
  await expect(payRow.getByTestId('pdc-deposit')).toBeVisible();
  await expect(payRow.getByTestId('pdc-return')).toBeVisible();
  await expect(panel.getByTestId('invoice-amount-paid')).toHaveText('AED 0.00');
});

test('same-day PDC deposit and clear posts cash', async ({ page }) => {
  test.setTimeout(120_000);
  const clientName = await registerFtaClient(page, 'pdc-clear');
  await createAndSendInvoice(page, clientName);
  await recordPdc(page, isoDate());

  const panel = await openPaymentList(page);
  const payRow = panel.locator('[data-testid^="payment-row-"]');
  await expect(payRow).toContainText('PENDING');
  await payRow.getByTestId('pdc-deposit').click();
  await expect(payRow.getByTestId('pdc-clear')).toBeVisible();
  await payRow.getByTestId('pdc-clear').click();
  await expect(payRow).toContainText('SUCCESS');
  await expect(payRow).toContainText('CLEARED');
  await expect(payRow).not.toContainText('not cash');
  await expect(payRow.getByTestId('pdc-clear')).toHaveCount(0);
  await expect(panel.getByTestId('invoice-amount-paid')).toHaveText('AED 210.00');
  await expect(panel.getByTestId('invoice-balance-due')).toHaveText('AED 0.00');

  await panel.locator('button').first().click();
  await expect(page.getByTestId('invoice-ar-panel')).toHaveCount(0);
  const row = invoiceRow(page);
  await expect(row.getByTestId('invoice-status')).toContainText(/PAID/);
  await expect(row.getByTestId('invoice-amount-paid')).toHaveText('AED 210.00');
});

test('bounce leaves invoice open and evaluates credit', async ({ page, request }) => {
  test.setTimeout(120_000);
  const clientName = await registerFtaClient(page, 'pdc-bounce');
  await createAndSendInvoice(page, clientName);
  await recordPdc(page, isoDate());

  const panel = await openPaymentList(page);
  const payRow = panel.locator('[data-testid^="payment-row-"]');
  await payRow.getByTestId('pdc-deposit').click();
  await expect(payRow.getByTestId('pdc-bounce')).toBeVisible();
  await payRow.getByTestId('pdc-bounce').click();
  await expect(payRow).toContainText('FAILED');
  await expect(payRow).toContainText('BOUNCED');
  await expect(payRow.getByTestId('pdc-bounce')).toHaveCount(0);
  await expect(panel.getByTestId('invoice-amount-paid')).toHaveText('AED 0.00');
  await expect(panel.getByTestId('invoice-balance-due')).toHaveText('AED 210.00');

  await panel.locator('button').first().click();
  await expect(page.getByTestId('invoice-ar-panel')).toHaveCount(0);
  const row = invoiceRow(page);
  await expect(row.getByTestId('invoice-status')).not.toContainText('PAID');
  await expect(row.getByTestId('invoice-amount-paid')).toHaveText('AED 0.00');
  await expect(row.getByTestId('invoice-balance-due')).toHaveText('AED 210.00');

  await page.getByTestId('nav-clients').click();
  const clientRow = page.getByTestId(`client-row-${clientName}`);
  await expect(clientRow.getByTestId('client-credit-status')).toBeVisible();
  await expect(clientRow.getByTestId('client-credit-status')).toContainText(
    /ACTIVE|WARNING|HOLD/,
  );

  const token = await pageAccessToken(page);
  const clients = await expectApiData<{ id: string; name: string }[]>(
    await authJson(request, 'GET', '/api/v1/clients?page=1&per_page=100', token),
    200,
  );
  const client = clients.find((entry) => entry.name === clientName);
  expect(client, 'bounce client missing').toBeTruthy();
  const credit = await expectApiData<{ credit_status: string }>(
    await authJson(request, 'GET', `/api/v1/clients/${client!.id}/credit`, token),
    200,
  );
  expect(['ACTIVE', 'WARNING', 'HOLD']).toContain(credit.credit_status);
});
