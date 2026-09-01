import { expect, test } from '@playwright/test';
import {
  authJson,
  createFtaSentInvoiceApi,
  expectApiData,
  putWorkspaceFtaApi,
  registerWorkspace,
} from './helpers';

test('cross-tenant credit note GET returns 404', async ({ request }) => {
  test.setTimeout(120_000);
  const workspaceA = await registerWorkspace(request, 'cn-iso-a');
  await putWorkspaceFtaApi(request, workspaceA.token);
  const sent = await createFtaSentInvoiceApi(request, workspaceA.token);
  const cn = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/credit-notes', workspaceA.token, {
      invoice_id: sent.invoiceId,
      reason: 'INVOICE_ERROR',
      items: [{ invoice_item_id: sent.itemId, quantity: '1' }],
    }),
    201,
  );

  const ownGet = await authJson(
    request,
    'GET',
    `/api/v1/credit-notes/${cn.id}`,
    workspaceA.token,
  );
  expect(ownGet.status(), await ownGet.text()).toBe(200);

  const workspaceB = await registerWorkspace(request, 'cn-iso-b');
  const foreignGet = await authJson(
    request,
    'GET',
    `/api/v1/credit-notes/${cn.id}`,
    workspaceB.token,
  );
  expect(foreignGet.status(), await foreignGet.text()).toBe(404);
  expect(foreignGet.status()).not.toBe(403);
});
