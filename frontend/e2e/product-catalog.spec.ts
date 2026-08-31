import { expect, test } from '@playwright/test';
import {
  PRODUCT_NAME,
  PRODUCT_SKU,
  createBrand,
  createCategory,
  createUom,
  registerViaUi,
  selectOptionContaining,
} from './helpers';

test('product master catalog happy path', async ({ page }) => {
  test.setTimeout(120_000);
  const { suffix } = await registerViaUi(page);
  const mpn = `DUC-4MM-${suffix}`;

  await page.getByTestId('nav-settings').click();
  await expect(page.getByTestId('settings-trn')).toBeVisible();
  await expect(async () => {
    expect(Number(await page.getByTestId('settings-tax-rate').inputValue())).toBe(5);
  }).toPass();

  await page.getByTestId('nav-products').click();
  await expect(page.getByRole('heading', { name: 'Product Master' })).toBeVisible();

  await createUom(page, 'MTR', 'Metre');
  await createUom(page, 'DRUM', 'Drum');
  await createCategory(page, 'Cables');
  await createBrand(page, 'Ducab');

  await page.getByTestId('tab-products').click();
  await page.getByTestId('add-product').click();
  await page.getByTestId('product-sku-input').fill(PRODUCT_SKU);
  await page.getByTestId('product-name-input').fill(PRODUCT_NAME);
  await selectOptionContaining(page, 'product-uom-select', 'MTR');
  await selectOptionContaining(page, 'product-category-select', 'Cables');
  await selectOptionContaining(page, 'product-brand-select', 'Ducab');
  await page.getByTestId('product-form-submit').click();
  await expect(page.getByTestId('catalog-modal')).toHaveCount(0);
  await expect(page.getByTestId(`product-row-${PRODUCT_SKU}`)).toBeVisible();

  await page.getByTestId(`product-row-${PRODUCT_SKU}`).click();
  await expect(page.getByTestId('product-detail')).toBeVisible();

  await page.getByTestId('identifier-type').selectOption('MPN');
  await page.getByTestId('identifier-value').fill(mpn);
  await page.getByTestId('identifier-add').click();
  await expect(page.getByTestId(`identifier-row-${mpn}`)).toBeVisible();

  await selectOptionContaining(page, 'conversion-uom', 'DRUM');
  await page.getByTestId('conversion-factor').fill('500');
  await page.getByTestId('conversion-add').click();
  await expect(page.getByTestId('conversion-label')).toContainText(/1 .+ = .+/);
  await expect(page.getByTestId('conversion-label')).toContainText('500');

  await page.getByTestId('price-type').selectOption('DEFAULT_SALES');
  await page.getByTestId('price-amount').fill('12.50');
  await page.getByTestId('price-add').click();
  await expect(page.getByTestId('price-row-DEFAULT_SALES')).toBeVisible();
  await expect(page.getByTestId('price-amount-display')).toContainText('AED 12.50');

  await page.reload();
  await expect(page.getByTestId(`product-row-${PRODUCT_SKU}`)).toBeVisible();
  await page.getByTestId(`product-row-${PRODUCT_SKU}`).click();
  await expect(page.getByTestId('product-detail')).toBeVisible();
  await expect(page.getByTestId(`identifier-row-${mpn}`)).toBeVisible();
  await expect(page.getByTestId('price-amount-display')).toContainText('AED 12.50');
});
