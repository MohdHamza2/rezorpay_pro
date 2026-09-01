import { expect, test } from '@playwright/test';
import {
  authJson,
  createFtaSentInvoiceApi,
  isoDate,
  putWorkspaceFtaApi,
  registerWorkspace,
} from './helpers';

test('cross-tenant AR statement GET returns 404', async ({ request }) => {
  test.setTimeout(120_000);
  const workspaceA = await registerWorkspace(request, 'ar-iso-a');
  await putWorkspaceFtaApi(request, workspaceA.token);
  const sent = await createFtaSentInvoiceApi(request, workspaceA.token);
  const today = isoDate();
  const path = `/api/v1/clients/${sent.clientId}/ar-statement?from=${today}&to=${today}`;

  const ownGet = await authJson(request, 'GET', path, workspaceA.token);
  expect(ownGet.status(), await ownGet.text()).toBe(200);

  const workspaceB = await registerWorkspace(request, 'ar-iso-b');
  const foreignGet = await authJson(request, 'GET', path, workspaceB.token);
  expect(foreignGet.status(), await foreignGet.text()).toBe(404);
  expect(foreignGet.status()).not.toBe(403);
});
