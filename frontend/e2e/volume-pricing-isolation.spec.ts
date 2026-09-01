import { expect, test } from '@playwright/test';
import { authJson, expectApiData, registerWorkspace, uniqueSuffix } from './helpers';

test('cross-tenant resolved-price GET returns 404', async ({ request }) => {
  test.setTimeout(120_000);
  const workspaceA = await registerWorkspace(request, 'vp-iso-a');
  const suffix = uniqueSuffix();
  const uom = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/products/uom', workspaceA.token, {
      code: `M-${suffix.slice(0, 6)}`,
      name: 'Metre',
    }),
    201,
  );
  const product = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/products', workspaceA.token, {
      internal_sku: `ISO-VP-${suffix}`,
      name: 'Isolated cable',
      base_uom_id: uom.id,
    }),
    201,
  );
  await expectApiData(
    await authJson(request, 'POST', `/api/v1/products/${product.id}/prices`, workspaceA.token, {
      price_type: 'DEFAULT_SALES',
      price: '100.00',
    }),
    201,
  );

  const ownGet = await authJson(
    request,
    'GET',
    `/api/v1/products/${product.id}/resolved-price?quantity=1`,
    workspaceA.token,
  );
  expect(ownGet.status(), await ownGet.text()).toBe(200);

  const workspaceB = await registerWorkspace(request, 'vp-iso-b');
  const foreignGet = await authJson(
    request,
    'GET',
    `/api/v1/products/${product.id}/resolved-price?quantity=1`,
    workspaceB.token,
  );
  expect(foreignGet.status(), await foreignGet.text()).toBe(404);
  expect(foreignGet.status()).not.toBe(403);
});
