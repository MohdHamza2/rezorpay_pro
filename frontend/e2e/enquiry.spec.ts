import { expect, test } from '@playwright/test';
import {
  API_URL,
  authJson,
  createClientViaUi,
  pageAccessToken,
  registerViaUi,
  uniqueEmail,
} from './helpers';

test('enquiry kanban, detail, and conversion to quotation', async ({ page }) => {
  test.setTimeout(120_000);
  const { suffix } = await registerViaUi(page, 'enq');
  const clientName = `Enquiry client ${suffix}`;

  await createClientViaUi(page, {
    name: clientName,
    email: uniqueEmail('enq-client'),
    address: 'Plot 5, Mussafah, Abu Dhabi',
  });

  // Navigate to Clients to get the ID, or we can just create the Enquiry with manual source and no client,
  // then verify it in UI.
  // Actually, let's create it via API
  const token = await pageAccessToken(page);
  
  const createResp = await authJson(page.request, 'POST', `/api/v1/enquiries`, token, {
    source: 'WHATSAPP',
    contact_name: 'WhatsApp Contact',
    contact_phone: '+1234567890',
    items_description: 'Hi, I need 5 units of 4mm cable',
  });
  expect(createResp.status()).toBe(201);
  const enquiry = await createResp.json();
  const enquiryId = enquiry.id;
  const enquiryNum = enquiry.enquiry_number;

  page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));
  page.on('pageerror', err => console.log('BROWSER ERROR:', err.message));

  await page.goto('/enquiries');
  
  // Wait for the Kanban board to load
  await page.waitForSelector('[class*="kanbanBoard"]', { timeout: 10000 }).catch(e => console.log('Kanban wait timeout:', e));
  
  // Verify Kanban board has the enquiry
  await expect(page.locator('[class*="kanbanBoard"]')).toBeVisible();
  await expect(page.locator(`text=${enquiryNum}`)).toBeVisible();

  // Click on the enquiry to view details
  await page.locator(`text=${enquiryNum}`).click();
  await expect(page).toHaveURL(new RegExp(`/enquiries/${enquiryId}$`));

  // Verify details
  await expect(page.locator(`text=${enquiryNum}`)).toBeVisible();
  await expect(page.locator('text=Hi, I need 5 units of 4mm cable')).toBeVisible();
  await expect(page.locator('text=WhatsApp Contact')).toBeVisible();
  
  // Try to start progress
  await page.locator('text=Start Progress').click();
  await expect(page.locator('text=IN PROGRESS')).toBeVisible();

  // Convert to quotation (should be disabled because no client is assigned)
  const convertBtn = page.locator('text=Convert to Quotation');
  await expect(convertBtn).toBeDisabled();

  // Let's update the enquiry via API to attach the client so we can test conversion
  // First, get client ID via API
  const clientsResp = await authJson(page.request, 'GET', `/api/v1/clients`, token);
  const clients = await clientsResp.json();
  const clientId = clients.data.find((c: any) => c.name === clientName).id;

  const updateResp = await authJson(page.request, 'PUT', `/api/v1/enquiries/${enquiryId}`, token, {
    client_id: clientId,
  });
  expect(updateResp.status()).toBe(200);

  // Reload page
  await page.reload();
  await expect(page.locator(`text=${clientName}`)).toBeVisible();

  // Now convert should be enabled
  await expect(convertBtn).toBeEnabled();
  
  // Listen for dialog
  page.on('dialog', dialog => dialog.accept());
  
  await convertBtn.click();

  // Should navigate to quotation detail
  await expect(page).toHaveURL(/\/quotations\//);
  await expect(page.getByTestId('quotation-status')).toContainText('DRAFT');
});
