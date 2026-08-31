import { expect, test } from '@playwright/test';
import { authJson, registerWorkspace, uniqueSuffix } from './helpers';

test('cross-tenant product GET returns 404', async ({ request }) => {
  const workspaceA = await registerWorkspace(request, 'iso-a');
  const uomRes = await authJson(request, 'POST', '/api/v1/products/uom', workspaceA.token, {
    code: 'MTR',
    name: 'Metre',
  });
  expect(uomRes.status(), await uomRes.text()).toBe(201);
  const uomId = (await uomRes.json()).data.id as string;

  const sku = `ISO-${uniqueSuffix()}`;
  const productRes = await authJson(request, 'POST', '/api/v1/products', workspaceA.token, {
    internal_sku: sku,
    name: 'Isolated cable',
    base_uom_id: uomId,
  });
  expect(productRes.status(), await productRes.text()).toBe(201);
  const productId = (await productRes.json()).data.id as string;

  const ownGet = await authJson(request, 'GET', `/api/v1/products/${productId}`, workspaceA.token);
  expect(ownGet.status(), await ownGet.text()).toBe(200);

  const workspaceB = await registerWorkspace(request, 'iso-b');
  const foreignGet = await authJson(
    request,
    'GET',
    `/api/v1/products/${productId}`,
    workspaceB.token,
  );
  expect(foreignGet.status(), await foreignGet.text()).toBe(404);
  expect(foreignGet.status()).not.toBe(403);
});
