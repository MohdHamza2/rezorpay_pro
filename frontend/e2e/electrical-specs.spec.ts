import { expect, test, type Page } from '@playwright/test';
import {
  authJson,
  createUom,
  pageAccessToken,
  registerViaUi,
  registerWorkspace,
  selectOptionContaining,
  waitForModalClosed,
} from './helpers';

async function createElectricalProduct(
  page: Page,
  input: {
    sku: string;
    name: string;
    uom: string;
    cores?: string;
    mm2?: string;
    amp?: string;
    poles?: string;
  },
): Promise<void> {
  await page.getByTestId('add-product').click();
  await page.getByTestId('product-sku-input').fill(input.sku);
  await page.getByTestId('product-name-input').fill(input.name);
  await selectOptionContaining(page, 'product-uom-select', input.uom);
  if (input.cores) await page.getByTestId('product-cores-input').fill(input.cores);
  if (input.mm2) await page.getByTestId('product-mm2-input').fill(input.mm2);
  if (input.amp) await page.getByTestId('product-amp-input').fill(input.amp);
  if (input.poles) await page.getByTestId('product-poles-input').fill(input.poles);
  await page.getByTestId('product-form-submit').click();
  await waitForModalClosed(page);
  await expect(page.getByTestId(`product-row-${input.sku}`)).toBeVisible();
}

async function applySpecFilters(
  page: Page,
  fields: { testId: string; value: string }[],
): Promise<void> {
  for (const field of fields) {
    await page.getByTestId(field.testId).fill(field.value);
  }
  await page.getByTestId('product-filter-apply').click();
}

async function expectOnlySku(page: Page, visibleSku: string, hiddenSku: string): Promise<void> {
  await expect(page.getByTestId(`product-row-${visibleSku}`)).toBeVisible();
  await expect(page.getByTestId(`product-row-${hiddenSku}`)).toHaveCount(0);
}

test('electrical spec filters separate cable and breaker', async ({ page, request }) => {
  test.setTimeout(120_000);
  const { suffix } = await registerViaUi(page, 'elec');
  const cableSku = `CBL-4C10-${suffix}`;
  const breakerSku = `MCB-63-3P-${suffix}`;

  await page.getByTestId('nav-products').click();
  await expect(page.getByRole('heading', { name: 'Product Master' })).toBeVisible();
  await createUom(page, 'PCS', 'Pieces');
  await page.getByTestId('tab-products').click();

  await createElectricalProduct(page, {
    sku: cableSku,
    name: '4-core 10mm XLPE',
    uom: 'PCS',
    cores: '4',
    mm2: '10',
  });
  await createElectricalProduct(page, {
    sku: breakerSku,
    name: '63A 3P MCB',
    uom: 'PCS',
    amp: '63',
    poles: '3',
  });

  const productId = await page.getByTestId(`product-row-${cableSku}`).getAttribute('data-product-id');
  expect(productId, 'missing cable product id').toBeTruthy();

  await applySpecFilters(page, [
    { testId: 'product-filter-mm2', value: '10' },
    { testId: 'product-filter-cores', value: '4' },
  ]);
  await expectOnlySku(page, cableSku, breakerSku);

  await page.getByTestId('product-filter-clear').click();
  await expect(page.getByTestId(`product-row-${cableSku}`)).toBeVisible();
  await expect(page.getByTestId(`product-row-${breakerSku}`)).toBeVisible();

  await applySpecFilters(page, [
    { testId: 'product-filter-amp', value: '63' },
    { testId: 'product-filter-poles', value: '3' },
  ]);
  await expectOnlySku(page, breakerSku, cableSku);

  const tokenA = await pageAccessToken(page);
  const ownGet = await authJson(request, 'GET', `/api/v1/products/${productId}`, tokenA);
  expect(ownGet.status(), await ownGet.text()).toBe(200);

  const workspaceB = await registerWorkspace(request, 'elec-iso-b');
  const foreignGet = await authJson(
    request,
    'GET',
    `/api/v1/products/${productId}`,
    workspaceB.token,
  );
  expect(foreignGet.status(), await foreignGet.text()).toBe(404);
  expect(foreignGet.status()).not.toBe(403);
});
