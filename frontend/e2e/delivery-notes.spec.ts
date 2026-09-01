import { expect, test } from '@playwright/test';
import {
  FTA_SELLER_ADDRESS,
  FTA_TRN,
  authJson,
  createCatalogLpoViaUi,
  createClientViaUi,
  createWarehouseBinViaApi,
  expectApiData,
  inventoryOnHand,
  isoDate,
  pageAccessToken,
  registerViaUi,
  registerWorkspace,
  seedCatalogOpeningStock,
  selectOptionContaining,
  uniqueEmail,
  uniqueSuffix,
} from './helpers';

test('catalog LPO delivery note confirm issues stock', async ({ page }) => {
  test.setTimeout(120_000);
  const { suffix } = await registerViaUi(page, 'dn');
  const clientName = `DN buyer ${suffix}`;
  const shipQty = '2';

  await page.getByTestId('nav-settings').click();
  await expect(page.getByTestId('settings-block-do-on-hold')).toBeChecked();

  await createClientViaUi(page, {
    name: clientName,
    email: uniqueEmail('dn-buyer'),
    address: 'Plot 4, Mussafah, Abu Dhabi',
  });

  const token = await pageAccessToken(page);
  const stock = await seedCatalogOpeningStock(page.request, token, suffix, '10');
  expect(await inventoryOnHand(page.request, token, stock.productId)).toBe(10);

  await createCatalogLpoViaUi(page, {
    clientName,
    sku: stock.sku,
    quantity: shipQty,
    price: '12.50',
  });
  await expect(page.getByTestId('lpo-status')).toContainText('DRAFT');
  await page.getByTestId('lpo-receive').click();
  await expect(page.getByTestId('lpo-status')).toContainText('RECEIVED');
  const lpoNumber = (await page.getByTestId('lpo-number').innerText()).trim();

  await page.getByTestId('nav-delivery-notes').click();
  await page.getByTestId('dn-create').click();
  await expect(page.getByTestId('dn-form')).toBeVisible();
  await page.getByTestId('dn-parent-type-lpo').check();
  await selectOptionContaining(page, 'dn-parent-select', lpoNumber);
  await selectOptionContaining(page, 'dn-warehouse', stock.warehouseCode);
  await expect(page.getByTestId('dn-remaining-0')).toHaveText(/^2(\.0+)?$/);
  await page.getByTestId('dn-form-submit').click();

  await expect(page.getByTestId('dn-detail')).toBeVisible();
  await expect(page.getByTestId('dn-status')).toContainText('DRAFT');
  await expect(page.getByTestId('dn-number')).toHaveText(/DN-\d{4}-\d{4}/);

  await page.getByTestId('dn-preview-pdf').click();
  await expect(page.getByTestId('dn-pdf-preview')).toBeVisible();
  await expect(page.getByTestId('dn-pdf-title')).toHaveText('Delivery Note');
  await expect(page.getByTestId('dn-pdf-title-ar')).toHaveText('إذن تسليم');
  await expect(page.getByTestId('dn-pdf-title')).not.toHaveText('Tax Invoice');
  await expect(page.getByTestId('pdf-title')).toHaveCount(0);
  await page.getByTestId('dn-pdf-preview-close').click();

  await page.getByTestId('dn-confirm').click();
  await expect(page.getByTestId('dn-status')).toContainText('CONFIRMED');
  await expect(page.getByTestId('credit-hold')).toHaveCount(0);
  expect(await inventoryOnHand(page.request, token, stock.productId)).toBe(8);
});

test('HOLD blocks DN confirm when block_do_on_hold', async ({ request }) => {
  test.setTimeout(120_000);
  const workspace = await registerWorkspace(request, 'dn-hold');
  await expectApiData(
    await authJson(request, 'PUT', '/api/v1/workspaces/me', workspace.token, {
      trn: FTA_TRN,
      address: FTA_SELLER_ADDRESS,
      block_do_on_hold: true,
      block_po_on_hold: false,
    }),
    200,
  );
  const client = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/clients', workspace.token, {
      name: 'COD DN client',
      email: uniqueEmail('dn-hold-client'),
      address: FTA_SELLER_ADDRESS,
      credit_limit: 0,
    }),
    201,
  );
  const today = isoDate();
  const invoice = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/invoices', workspace.token, {
      client_id: client.id,
      issue_date: today,
      due_date: today,
      supply_date: today,
      items: [{ description: 'COD opener', quantity: '1', unit_price: '50.00' }],
    }),
    201,
  );
  await expectApiData(
    await authJson(request, 'POST', `/api/v1/invoices/${invoice.id}/send`, workspace.token, {}),
    200,
  );

  const loc = await createWarehouseBinViaApi(request, workspace.token, uniqueSuffix());
  const lpo = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/customer-purchase-orders', workspace.token, {
      client_id: client.id,
      lpo_date: isoDate(),
      currency: 'AED',
      items: [{ description: 'Ad-hoc ship line', quantity: '3', unit_price: '10.00' }],
    }),
    201,
  );
  await expectApiData(
    await authJson(
      request,
      'POST',
      `/api/v1/customer-purchase-orders/${lpo.id}/receive`,
      workspace.token,
      {},
    ),
    200,
  );
  const dn = await expectApiData<{ id: string; status: string }>(
    await authJson(request, 'POST', '/api/v1/delivery-notes', workspace.token, {
      warehouse_id: loc.warehouseId,
      customer_purchase_order_id: lpo.id,
    }),
    201,
  );

  const blocked = await authJson(
    request,
    'POST',
    `/api/v1/delivery-notes/${dn.id}/confirm`,
    workspace.token,
    {},
  );
  const blockedBody = JSON.parse(await blocked.text()) as {
    error?: { code?: string };
  };
  expect(blocked.status()).toBe(400);
  expect(blockedBody.error?.code).toBe('CREDIT_HOLD');

  await expectApiData(
    await authJson(request, 'PUT', '/api/v1/workspaces/me', workspace.token, {
      block_do_on_hold: false,
    }),
    200,
  );
  await expectApiData(
    await authJson(
      request,
      'POST',
      `/api/v1/delivery-notes/${dn.id}/confirm`,
      workspace.token,
      {},
    ),
    200,
  );
});
