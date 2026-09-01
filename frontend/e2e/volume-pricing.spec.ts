import { expect, test, type Page } from '@playwright/test';
import {
  PRODUCT_NAME,
  authJson,
  createBrand,
  createCategory,
  createClientViaUi,
  createUom,
  expectApiData,
  pageAccessToken,
  registerViaUi,
  selectOptionContaining,
  uniqueEmail,
} from './helpers';

async function expectLinePrice(page: Page, amount: string, source: string): Promise<void> {
  await expect(page.getByTestId('invoice-item-0-price')).toHaveValue(amount);
  await expect(page.getByTestId('invoice-item-0-price-source')).toHaveText(source);
}

test('invoice catalog line uses customer then volume then override', async ({ page }) => {
  test.setTimeout(180_000);
  const { suffix } = await registerViaUi(page, 'volume');
  const sku = `VP-${suffix.slice(0, 8)}`;
  const clientAName = `Dealer A ${suffix}`;
  const clientBName = `Dealer B ${suffix}`;

  await createClientViaUi(page, {
    name: clientAName,
    email: uniqueEmail('vol-a'),
  });
  await createClientViaUi(page, {
    name: clientBName,
    email: uniqueEmail('vol-b'),
  });

  await page.getByTestId('nav-products').click();
  await expect(page.getByRole('heading', { name: 'Product Master' })).toBeVisible();

  await createUom(page, 'MTR', 'Metre');
  await createCategory(page, 'Cables');
  await createBrand(page, 'Ducab');

  await page.getByTestId('tab-products').click();
  await page.getByTestId('add-product').click();
  await page.getByTestId('product-sku-input').fill(sku);
  await page.getByTestId('product-name-input').fill(PRODUCT_NAME);
  await selectOptionContaining(page, 'product-uom-select', 'MTR');
  await selectOptionContaining(page, 'product-category-select', 'Cables');
  await selectOptionContaining(page, 'product-brand-select', 'Ducab');
  await page.getByTestId('product-form-submit').click();
  await expect(page.getByTestId('catalog-modal')).toHaveCount(0);
  await expect(page.getByTestId(`product-row-${sku}`)).toBeVisible();

  await page.getByTestId(`product-row-${sku}`).click();
  await expect(page.getByTestId('product-detail')).toBeVisible();
  await page.getByTestId('price-type').selectOption('DEFAULT_SALES');
  await page.getByTestId('price-amount').fill('100.00');
  await page.getByTestId('price-add').click();
  await expect(page.getByTestId('price-row-DEFAULT_SALES')).toBeVisible();

  const token = await pageAccessToken(page);
  const clients = await expectApiData<{ id: string; name: string }[]>(
    await authJson(page.request, 'GET', '/api/v1/clients?per_page=100', token),
    200,
  );
  const clientA = clients.find((row) => row.name === clientAName);
  expect(clientA, 'missing client A').toBeTruthy();

  const products = await expectApiData<{ id: string; internal_sku: string }[]>(
    await authJson(
      page.request,
      'GET',
      `/api/v1/products?search=${encodeURIComponent(sku)}&per_page=100`,
      token,
    ),
    200,
  );
  const product = products.find((row) => row.internal_sku === sku);
  expect(product, 'missing catalog product').toBeTruthy();

  await expectApiData(
    await authJson(page.request, 'POST', `/api/v1/products/${product!.id}/prices`, token, {
      price_type: 'TIER_1',
      price: '90.00',
      min_quantity: '10',
    }),
    201,
  );
  await expectApiData(
    await authJson(page.request, 'POST', `/api/v1/products/${product!.id}/prices`, token, {
      price_type: 'CUSTOMER_SPECIFIC',
      price: '80.00',
      client_id: clientA!.id,
      min_quantity: '1',
    }),
    201,
  );

  await page.getByTestId('nav-invoices').click();
  await page.getByTestId('invoice-create').click();
  await expect(page.getByTestId('invoice-modal')).toBeVisible();
  await selectOptionContaining(page, 'invoice-client-select', clientAName);
  await selectOptionContaining(page, 'invoice-item-0-product', sku);
  await expectLinePrice(page, '80.00', 'Customer');

  await page.getByTestId('invoice-item-0-quantity').fill('10');
  await expect(page.getByTestId('invoice-item-0-quantity')).toHaveValue('10');
  await expectLinePrice(page, '80.00', 'Customer');

  await selectOptionContaining(page, 'invoice-client-select', clientBName);
  await expectLinePrice(page, '90.00', 'Volume');

  await page.getByTestId('invoice-item-0-price').fill('12.50');
  await expect(page.getByTestId('invoice-item-0-price')).toHaveValue('12.50');
  await expect(page.getByTestId('invoice-item-0-price-source')).toHaveText('Override');

  await page.getByTestId('invoice-item-0-quantity').fill('5');
  await expect(page.getByTestId('invoice-item-0-quantity')).toHaveValue('5');
  await expect(page.getByTestId('invoice-item-0-price')).toHaveValue('12.50');
  await expect(page.getByTestId('invoice-item-0-price-source')).toHaveText('Override');
});
