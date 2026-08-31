import { expect, test } from '@playwright/test';
import {
  authJson,
  createWarehouseBinViaApi,
  expectApiData,
  isoDate,
  registerWorkspace,
  uniqueSuffix,
} from './helpers';

test('cross-tenant delivery note GET returns 404', async ({ request }) => {
  test.setTimeout(120_000);
  const workspaceA = await registerWorkspace(request, 'dn-iso-a');
  const client = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/clients', workspaceA.token, {
      name: 'Client A',
      email: `dn-client-a.${Date.now()}@example.com`,
      address: 'Warehouse 12, Al Quoz, Dubai',
    }),
    201,
  );
  const loc = await createWarehouseBinViaApi(request, workspaceA.token, uniqueSuffix());
  const lpo = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/customer-purchase-orders', workspaceA.token, {
      client_id: client.id,
      lpo_date: isoDate(),
      currency: 'AED',
      items: [{ description: 'NYA 4mm cable', quantity: '2', unit_price: '100.00' }],
    }),
    201,
  );
  await expectApiData(
    await authJson(
      request,
      'POST',
      `/api/v1/customer-purchase-orders/${lpo.id}/receive`,
      workspaceA.token,
      {},
    ),
    200,
  );
  const dn = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/delivery-notes', workspaceA.token, {
      warehouse_id: loc.warehouseId,
      customer_purchase_order_id: lpo.id,
    }),
    201,
  );

  const ownGet = await authJson(
    request,
    'GET',
    `/api/v1/delivery-notes/${dn.id}`,
    workspaceA.token,
  );
  expect(ownGet.status(), await ownGet.text()).toBe(200);

  const workspaceB = await registerWorkspace(request, 'dn-iso-b');
  const foreignGet = await authJson(
    request,
    'GET',
    `/api/v1/delivery-notes/${dn.id}`,
    workspaceB.token,
  );
  expect(foreignGet.status(), await foreignGet.text()).toBe(404);
  expect(foreignGet.status()).not.toBe(403);
});
