import { expect, test, type APIRequestContext, type APIResponse } from '@playwright/test';
import {
  authJson,
  createFtaSentInvoiceApi,
  expectApiData,
  isoDate,
  putWorkspaceFtaApi,
  registerWorkspace,
  uniqueSuffix,
} from './helpers';

async function expectNotFound(response: APIResponse): Promise<void> {
  expect(response.status(), await response.text()).toBe(404);
  expect(response.status()).not.toBe(403);
}

async function postPdc(
  request: APIRequestContext,
  token: string,
  invoiceId: string,
  paymentId: string,
  action: string,
): Promise<APIResponse> {
  return authJson(
    request,
    'POST',
    `/api/v1/invoices/${invoiceId}/payments/${paymentId}/pdc/${action}`,
    token,
    {},
  );
}

test('cross-tenant PDC actions 404 and PUT is 405 in-workspace', async ({ request }) => {
  test.setTimeout(120_000);
  const workspaceA = await registerWorkspace(request, 'pdc-iso-a');
  await putWorkspaceFtaApi(request, workspaceA.token);
  const sent = await createFtaSentInvoiceApi(request, workspaceA.token);
  const payment = await expectApiData<{ id: string }>(
    await authJson(
      request,
      'POST',
      `/api/v1/invoices/${sent.invoiceId}/payments`,
      workspaceA.token,
      {
        amount: '10.00',
        payment_method: 'PDC',
        pdc_date: isoDate(),
      },
      { 'Idempotency-Key': `pdc-${uniqueSuffix()}` },
    ),
    200,
  );

  const workspaceB = await registerWorkspace(request, 'pdc-iso-b');
  for (const action of ['deposit', 'clear', 'bounce', 'return'] as const) {
    const foreign = await postPdc(
      request,
      workspaceB.token,
      sent.invoiceId,
      payment.id,
      action,
    );
    await expectNotFound(foreign);
  }

  const foreignPut = await authJson(
    request,
    'PUT',
    `/api/v1/invoices/${sent.invoiceId}/payments/${payment.id}`,
    workspaceB.token,
    { status: 'SUCCESS' },
  );
  await expectNotFound(foreignPut);
  expect(foreignPut.status()).not.toBe(405);

  const ownPut = await authJson(
    request,
    'PUT',
    `/api/v1/invoices/${sent.invoiceId}/payments/${payment.id}`,
    workspaceA.token,
    { status: 'SUCCESS' },
  );
  const putStatus = ownPut.status();
  const putBody = await ownPut.text();
  if (putStatus === 422) {
    expect(putStatus, putBody).not.toBe(200);
  } else {
    expect(putStatus, putBody).toBe(405);
  }
  expect(putStatus).not.toBe(200);
});
