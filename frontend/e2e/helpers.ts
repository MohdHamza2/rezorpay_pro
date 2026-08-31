import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const API_URL = process.env.VITE_API_URL || 'http://localhost:8000';
export const E2E_PASSWORD = 'Passw0rd1';
export const PRODUCT_SKU = 'CBL-4MM-001';
export const PRODUCT_NAME = 'NYA 4mm2 cable';

export function uniqueSuffix(): string {
  return `${Date.now()}${Math.random().toString(36).slice(2, 6)}`;
}

export function uniqueEmail(prefix: string): string {
  return `${prefix}.${uniqueSuffix()}@example.com`;
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

export async function registerViaUi(page: Page): Promise<{ email: string; suffix: string }> {
  const suffix = uniqueSuffix();
  const email = uniqueEmail('catalog');
  await page.goto('/register');
  await page.locator('#name').fill(`E2E User ${suffix}`);
  await page.locator('#email').fill(email);
  await page.locator('#password').fill(E2E_PASSWORD);
  await page.locator('#workspace_name').fill(`E2E Catalog ${suffix}`);
  await page.getByTestId('register-submit').click();
  await expect(page.getByTestId('app-layout')).toBeVisible();
  return { email, suffix };
}

export async function registerWorkspace(
  request: APIRequestContext,
  label: string,
): Promise<{ token: string; email: string }> {
  const email = uniqueEmail(label);
  const response = await request.post(`${API_URL}/auth/register`, {
    data: {
      name: `Owner ${label}`,
      email,
      password: E2E_PASSWORD,
      workspace_name: `Workspace ${label} ${uniqueSuffix()}`,
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const body = await response.json();
  return { token: body.data.access_token as string, email };
}

export async function authJson(
  request: APIRequestContext,
  method: 'GET' | 'POST',
  path: string,
  token: string,
  data?: unknown,
) {
  const response = await request.fetch(`${API_URL}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    ...(data !== undefined ? { data } : {}),
  });
  return response;
}
