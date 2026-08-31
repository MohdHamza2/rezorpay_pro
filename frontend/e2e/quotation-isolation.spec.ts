import { expect, test } from '@playwright/test';
import { authJson, isoDate, registerWorkspace } from './helpers';

test('cross-tenant quotation GET returns 404', async ({ request }) => {
  const workspaceA = await registerWorkspace(request, 'quo-iso-a');
  const clientRes = await authJson(request, 'POST', '/api/v1/clients', workspaceA.token, {
    name: 'Client A',
    email: `quo-client-a.${Date.now()}@example.com`,
    address: 'Warehouse 12, Al Quoz, Dubai',
  });
  expect(clientRes.status(), await clientRes.text()).toBe(201);
  const clientId = (await clientRes.json()).data.id as string;

  const quoteRes = await authJson(request, 'POST', '/api/v1/quotations', workspaceA.token, {
    client_id: clientId,
    quotation_date: isoDate(),
    valid_until: isoDate(14),
    currency: 'AED',
    items: [{ description: 'NYA 4mm cable', quantity: '1', unit_price: '10.00' }],
  });
  expect(quoteRes.status(), await quoteRes.text()).toBe(201);
  const quoteId = (await quoteRes.json()).data.id as string;

  const ownGet = await authJson(request, 'GET', `/api/v1/quotations/${quoteId}`, workspaceA.token);
  expect(ownGet.status(), await ownGet.text()).toBe(200);

  const workspaceB = await registerWorkspace(request, 'quo-iso-b');
  const foreignGet = await authJson(
    request,
    'GET',
    `/api/v1/quotations/${quoteId}`,
    workspaceB.token,
  );
  expect(foreignGet.status(), await foreignGet.text()).toBe(404);
  expect(foreignGet.status()).not.toBe(403);
});
