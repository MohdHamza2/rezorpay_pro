import { expect, test } from '@playwright/test';
import { authJson, isoDate, registerWorkspace } from './helpers';

test('cross-tenant LPO GET returns 404', async ({ request }) => {
  const workspaceA = await registerWorkspace(request, 'lpo-iso-a');
  const clientRes = await authJson(request, 'POST', '/api/v1/clients', workspaceA.token, {
    name: 'Client A',
    email: `lpo-client-a.${Date.now()}@example.com`,
    address: 'Warehouse 12, Al Quoz, Dubai',
  });
  expect(clientRes.status(), await clientRes.text()).toBe(201);
  const clientId = (await clientRes.json()).data.id as string;

  const lpoRes = await authJson(request, 'POST', '/api/v1/customer-purchase-orders', workspaceA.token, {
    client_id: clientId,
    lpo_date: isoDate(),
    currency: 'AED',
    items: [{ description: 'NYA 4mm cable', quantity: '2', unit_price: '100.00' }],
  });
  expect(lpoRes.status(), await lpoRes.text()).toBe(201);
  const lpoId = (await lpoRes.json()).data.id as string;

  const ownGet = await authJson(
    request,
    'GET',
    `/api/v1/customer-purchase-orders/${lpoId}`,
    workspaceA.token,
  );
  expect(ownGet.status(), await ownGet.text()).toBe(200);

  const workspaceB = await registerWorkspace(request, 'lpo-iso-b');
  const foreignGet = await authJson(
    request,
    'GET',
    `/api/v1/customer-purchase-orders/${lpoId}`,
    workspaceB.token,
  );
  expect(foreignGet.status(), await foreignGet.text()).toBe(404);
  expect(foreignGet.status()).not.toBe(403);
});
