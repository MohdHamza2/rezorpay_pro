import { expect, test } from '@playwright/test';
import { authJson, registerWorkspace } from './helpers';

test('cross-tenant client credit GET returns 404', async ({ request }) => {
  test.setTimeout(120_000);
  const workspaceA = await registerWorkspace(request, 'credit-iso-a');
  const clientRes = await authJson(request, 'POST', '/api/v1/clients', workspaceA.token, {
    name: 'Client A',
    email: `credit-client-a.${Date.now()}@example.com`,
    address: 'Warehouse 12, Al Quoz, Dubai',
    credit_limit: 0,
  });
  expect(clientRes.status(), await clientRes.text()).toBe(201);
  const clientId = (await clientRes.json()).data.id as string;

  const ownGet = await authJson(
    request,
    'GET',
    `/api/v1/clients/${clientId}/credit`,
    workspaceA.token,
  );
  expect(ownGet.status(), await ownGet.text()).toBe(200);

  const workspaceB = await registerWorkspace(request, 'credit-iso-b');
  const foreignGet = await authJson(
    request,
    'GET',
    `/api/v1/clients/${clientId}/credit`,
    workspaceB.token,
  );
  expect(foreignGet.status(), await foreignGet.text()).toBe(404);
  expect(foreignGet.status()).not.toBe(403);
});
