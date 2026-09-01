import { expect, type APIRequestContext, type APIResponse, type Page } from '@playwright/test';

export const API_URL = process.env.VITE_API_URL || 'http://localhost:8000';
export const E2E_PASSWORD = 'Passw0rd1';
export const PRODUCT_SKU = 'CBL-4MM-001';
export const PRODUCT_NAME = 'NYA 4mm2 cable';
export const FTA_TRN = '100123456789003';
export const FTA_SELLER_ADDRESS = 'Warehouse 12, Al Quoz, Dubai';
export const FTA_BUYER_ADDRESS = 'Plot 4, Mussafah, Abu Dhabi';

export function uniqueSuffix(): string {
  return `${Date.now()}${Math.random().toString(36).slice(2, 6)}`;
}

export function uniqueEmail(prefix: string): string {
  return `${prefix}.${uniqueSuffix()}@example.com`;
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export async function waitForModalClosed(page: Page): Promise<void> {
  await expect(page.getByTestId('catalog-modal')).toHaveCount(0);
}

export async function selectOptionContaining(
  page: Page,
  testId: string,
  text: string,
): Promise<void> {
  const select = page.getByTestId(testId);
  const option = select.locator('option').filter({ hasText: text }).last();
  await expect(option).toBeAttached();
  const value = await option.getAttribute('value');
  expect(value, `missing option ${text}`).toBeTruthy();
  await select.selectOption(value as string);
}

export async function createUom(page: Page, code: string, name: string): Promise<void> {
  await page.getByTestId('tab-uoms').click();
  await page.getByTestId('add-uom').click();
  await page.getByTestId('uom-code-input').fill(code);
  await page.getByTestId('uom-name-input').fill(name);
  await page.getByTestId('uom-form-submit').click();
  await waitForModalClosed(page);
  await expect(page.getByTestId(`uom-row-${code}`)).toBeVisible();
}

export async function createCategory(page: Page, name: string): Promise<void> {
  await page.getByTestId('tab-categories').click();
  await page.getByTestId('add-category').click();
  await page.getByTestId('category-name-input').fill(name);
  await page.getByTestId('category-form-submit').click();
  await waitForModalClosed(page);
  await expect(page.getByTestId(`category-row-${name}`)).toBeVisible();
}

export async function createBrand(page: Page, name: string): Promise<void> {
  await page.getByTestId('tab-brands').click();
  await page.getByTestId('add-brand').click();
  await page.getByTestId('brand-name-input').fill(name);
  await page.getByTestId('brand-form-submit').click();
  await waitForModalClosed(page);
  await expect(page.getByTestId(`brand-row-${name}`)).toBeVisible();
}

export async function registerViaUi(
  page: Page,
  prefix = 'catalog',
): Promise<{ email: string; suffix: string }> {
  const suffix = uniqueSuffix();
  const email = uniqueEmail(prefix);
  await page.goto('/register');
  await page.locator('#name').fill(`E2E User ${suffix}`);
  await page.locator('#email').fill(email);
  await page.locator('#password').fill(E2E_PASSWORD);
  await page.locator('#workspace_name').fill(`E2E ${prefix} ${suffix}`);
  await submitRegisterUntilReady(page);
  return { email, suffix };
}

async function submitRegisterUntilReady(page: Page): Promise<void> {
  for (let attempt = 0; attempt < 5; attempt++) {
    await page.getByTestId('register-submit').click();
    const layout = page.getByTestId('app-layout');
    try {
      await expect(layout).toBeVisible({ timeout: 20_000 });
      return;
    } catch {
      const limited = await page.getByText(/rate limit/i).isVisible();
      if (!limited && attempt === 4) throw new Error('register did not reach app layout');
      await sleep(16_000);
    }
  }
}

export async function registerWorkspace(
  request: APIRequestContext,
  label: string,
): Promise<{ token: string; email: string }> {
  const email = uniqueEmail(label);
  const response = await postRegisterWithRetry(request, label, email);
  const body = await response.json();
  return { token: body.data.access_token as string, email };
}

async function postRegisterWithRetry(
  request: APIRequestContext,
  label: string,
  email: string,
) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const response = await request.post(`${API_URL}/auth/register`, {
      data: {
        name: `Owner ${label}`,
        email,
        password: E2E_PASSWORD,
        workspace_name: `Workspace ${label} ${uniqueSuffix()}`,
      },
    });
    if (response.status() === 429) {
      await sleep(16_000);
      continue;
    }
    expect(response.ok(), await response.text()).toBeTruthy();
    return response;
  }
  throw new Error('register rate-limited after retries');
}

export async function authJson(
  request: APIRequestContext,
  method: 'GET' | 'POST' | 'PUT',
  path: string,
  token: string,
  data?: unknown,
) {
  return request.fetch(`${API_URL}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    ...(data !== undefined ? { data } : {}),
  });
}

export type WorkspaceCreditSettings = {
  limitDefault?: string;
  warningDays?: string;
  holdDays?: string;
  blockPoOnHold?: boolean;
};

async function applyCreditSettings(page: Page, credit?: WorkspaceCreditSettings): Promise<void> {
  if (!credit) return;
  if (credit.limitDefault !== undefined) {
    await page.getByTestId('settings-credit-limit-default').fill(credit.limitDefault);
  }
  if (credit.warningDays !== undefined) {
    await page.getByTestId('settings-credit-warning-days').fill(credit.warningDays);
  }
  if (credit.holdDays !== undefined) {
    await page.getByTestId('settings-credit-hold-days').fill(credit.holdDays);
  }
  if (credit.blockPoOnHold === true) {
    await page.getByTestId('settings-block-po-on-hold').check();
  } else if (credit.blockPoOnHold === false) {
    await page.getByTestId('settings-block-po-on-hold').uncheck();
  }
}

export async function saveWorkspaceFta(
  page: Page,
  credit?: WorkspaceCreditSettings,
): Promise<void> {
  await page.getByTestId('nav-settings').click();
  await expect(page.getByTestId('settings-trn')).toBeVisible();
  await expect(async () => {
    expect(Number(await page.getByTestId('settings-tax-rate').inputValue())).toBe(5);
  }).toPass();
  await page.getByTestId('settings-trn').fill(FTA_TRN);
  await page.getByTestId('settings-address').fill(FTA_SELLER_ADDRESS);
  await applyCreditSettings(page, credit);
  await page.getByTestId('settings-save').click();
  await expect(page.getByText('Settings updated successfully')).toBeVisible();
}

export async function createClientViaUi(
  page: Page,
  input: {
    name: string;
    email: string;
    address?: string;
    taxId?: string;
    creditLimit?: string;
  },
): Promise<void> {
  await page.getByTestId('nav-clients').click();
  await page.getByTestId('client-add').click();
  await page.getByTestId('client-name').fill(input.name);
  await page.getByTestId('client-email').fill(input.email);
  if (input.address) await page.getByTestId('client-address').fill(input.address);
  if (input.taxId) await page.getByTestId('client-tax-id').fill(input.taxId);
  if (input.creditLimit !== undefined) {
    await page.getByTestId('client-credit-limit').fill(input.creditLimit);
  }
  await page.getByTestId('client-form-submit').click();
  await expect(page.getByTestId('client-modal')).toHaveCount(0);
  await expect(page.getByTestId(`client-row-${input.name}`)).toBeVisible();
}

export async function pageAccessToken(page: Page): Promise<string> {
  const token = await page.evaluate(() => {
    const raw = window.localStorage.getItem('auth_tokens');
    if (!raw) return '';
    try {
      return (JSON.parse(raw) as { access_token?: string }).access_token ?? '';
    } catch {
      return '';
    }
  });
  expect(token, 'missing access_token').toBeTruthy();
  return token;
}

export async function createAdhocQuotationViaUi(
  page: Page,
  input: { clientName: string; description: string; quantity: string; price: string },
): Promise<void> {
  await page.getByTestId('nav-quotations').click();
  await page.getByTestId('quotation-create').click();
  await expect(page.getByTestId('quotation-form')).toBeVisible();
  await selectOptionContaining(page, 'quotation-client-select', input.clientName);
  await page.getByTestId('quotation-item-0-description').fill(input.description);
  await page.getByTestId('quotation-item-0-quantity').fill(input.quantity);
  await page.getByTestId('quotation-item-0-price').fill(input.price);
  await page.getByTestId('quotation-form-submit').click();
  await expect(page.getByTestId('quotation-detail')).toBeVisible();
}

export async function createAdhocLpoViaUi(
  page: Page,
  input: { clientName: string; description: string; quantity: string; price: string },
): Promise<void> {
  await page.getByTestId('nav-lpos').click();
  await page.getByTestId('lpo-create').click();
  await expect(page.getByTestId('lpo-form')).toBeVisible();
  await selectOptionContaining(page, 'lpo-client-select', input.clientName);
  await page.getByTestId('lpo-item-0-description').fill(input.description);
  await page.getByTestId('lpo-item-0-quantity').fill(input.quantity);
  await page.getByTestId('lpo-item-0-price').fill(input.price);
  await page.getByTestId('lpo-form-submit').click();
  await expect(page.getByTestId('lpo-detail')).toBeVisible();
}

export async function createAdhocInvoiceViaUi(
  page: Page,
  input: { clientName: string; description: string; quantity: string; price: string },
): Promise<void> {
  await page.getByTestId('nav-invoices').click();
  await page.getByTestId('invoice-create').click();
  await expect(page.getByTestId('invoice-modal')).toBeVisible();
  await selectOptionContaining(page, 'invoice-client-select', input.clientName);
  const issue = await page.getByTestId('invoice-issue-date').inputValue();
  await page.getByTestId('invoice-supply-date').fill(issue);
  await page.getByTestId('invoice-item-0-description').fill(input.description);
  await page.getByTestId('invoice-item-0-quantity').fill(input.quantity);
  await page.getByTestId('invoice-item-0-price').fill(input.price);
  await page.getByTestId('invoice-due-date').fill(issue);
  await page.getByTestId('invoice-form-submit').click();
  await expect(page.getByTestId('invoice-modal')).toHaveCount(0);
  await expect(page.locator('[data-testid^="invoice-row-"]').first()).toBeVisible();
}

export function draftInvoiceRow(page: Page) {
  return page.locator('[data-testid^="invoice-row-"]').filter({
    has: page.getByTestId('invoice-send'),
  });
}

export function isoDate(offsetDays = 0): string {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  return date.toISOString().slice(0, 10);
}

export async function expectApiData<T>(
  response: APIResponse,
  allowed: number | readonly number[],
): Promise<T> {
  const text = await response.text();
  const statuses = typeof allowed === 'number' ? [allowed] : [...allowed];
  expect(statuses, text).toContain(response.status());
  return (JSON.parse(text) as { data: T }).data;
}

export async function createWarehouseBinViaApi(
  request: APIRequestContext,
  token: string,
  suffix: string,
): Promise<{ warehouseId: string; warehouseCode: string; binId: string }> {
  const warehouseCode = `WH-${suffix.slice(0, 8)}`;
  const warehouse = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/inventory/warehouses', token, {
      code: warehouseCode,
      name: 'Main warehouse',
    }),
    [200, 201],
  );
  const bin = await expectApiData<{ id: string }>(
    await authJson(
      request,
      'POST',
      `/api/v1/inventory/warehouses/${warehouse.id}/bins`,
      token,
      { code: 'A-01' },
    ),
    [200, 201],
  );
  return { warehouseId: warehouse.id, warehouseCode, binId: bin.id };
}

export async function seedCatalogOpeningStock(
  request: APIRequestContext,
  token: string,
  suffix: string,
  opening = '10',
): Promise<{
  productId: string;
  sku: string;
  warehouseId: string;
  warehouseCode: string;
  binId: string;
}> {
  const sku = `CBL-DN-${suffix.slice(0, 8)}`;
  const uom = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/products/uom', token, {
      code: `M-${suffix.slice(0, 6)}`,
      name: 'Metre',
    }),
    201,
  );
  const product = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/products', token, {
      name: PRODUCT_NAME,
      internal_sku: sku,
      base_uom_id: uom.id,
    }),
    201,
  );
  const loc = await createWarehouseBinViaApi(request, token, suffix);
  await expectApiData(
    await authJson(request, 'POST', '/api/v1/inventory/adjust', token, {
      product_id: product.id,
      warehouse_id: loc.warehouseId,
      bin_id: loc.binId,
      quantity: opening,
      reason: 'OPENING',
      notes: 'Opening stock',
    }),
    200,
  );
  return { productId: product.id, sku, ...loc };
}

export async function inventoryOnHand(
  request: APIRequestContext,
  token: string,
  productId: string,
): Promise<number> {
  const rows = await expectApiData<{ on_hand: string | number }[]>(
    await authJson(
      request,
      'GET',
      `/api/v1/inventory/levels?product_id=${productId}`,
      token,
    ),
    200,
  );
  return rows.reduce((sum, row) => sum + Number(row.on_hand ?? 0), 0);
}

export async function putWorkspaceFtaApi(
  request: APIRequestContext,
  token: string,
): Promise<void> {
  await expectApiData(
    await authJson(request, 'PUT', '/api/v1/workspaces/me', token, {
      trn: FTA_TRN,
      address: FTA_SELLER_ADDRESS,
      credit_limit_default: '100000.00',
    }),
    200,
  );
}

export async function createFtaSentInvoiceApi(
  request: APIRequestContext,
  token: string,
): Promise<{ clientId: string; invoiceId: string; itemId: string }> {
  const client = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/clients', token, {
      name: 'Client A',
      email: uniqueEmail('cn-iso-client'),
      address: FTA_BUYER_ADDRESS,
    }),
    201,
  );
  const today = isoDate();
  const created = await expectApiData<{ id: string }>(
    await authJson(request, 'POST', '/api/v1/invoices', token, {
      client_id: client.id,
      issue_date: today,
      due_date: today,
      supply_date: today,
      items: [{ description: 'NYA 4mm cable', quantity: '2', unit_price: '100.00' }],
    }),
    201,
  );
  const sent = await expectApiData<{ id: string; items: { id: string }[] }>(
    await authJson(request, 'POST', `/api/v1/invoices/${created.id}/send`, token, {}),
    200,
  );
  return { clientId: client.id, invoiceId: sent.id, itemId: sent.items[0].id };
}

export async function createCatalogLpoViaUi(
  page: Page,
  input: { clientName: string; sku: string; quantity: string; price: string },
): Promise<void> {
  await page.getByTestId('nav-lpos').click();
  await page.getByTestId('lpo-create').click();
  await expect(page.getByTestId('lpo-form')).toBeVisible();
  await selectOptionContaining(page, 'lpo-client-select', input.clientName);
  await selectOptionContaining(page, 'lpo-item-0-product', input.sku);
  await page.getByTestId('lpo-item-0-quantity').fill(input.quantity);
  await page.getByTestId('lpo-item-0-price').fill(input.price);
  await page.getByTestId('lpo-form-submit').click();
  await expect(page.getByTestId('lpo-detail')).toBeVisible();
}
