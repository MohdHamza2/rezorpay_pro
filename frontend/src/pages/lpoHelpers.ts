import { z } from 'zod';
import type { CustomerPurchaseOrder, LpoCreatePayload, LpoItem, LpoItemWrite, LpoUpdatePayload } from '../api/lpos';
import { parseAmount, todayIso } from './quotationHelpers';

export type LpoLineForm = {
  product_id?: string;
  description?: string;
  quantity: string;
  unit_price?: string;
  tax_rate?: string;
  discount_percent?: string;
  discount_amount?: string;
};

function addRateAndDiscountIssues(item: LpoLineForm, ctx: z.RefinementCtx) {
  const tax = parseAmount(item.tax_rate);
  if (item.tax_rate?.trim() && (tax === undefined || tax < 0 || tax > 100)) {
    ctx.addIssue({ code: 'custom', message: 'Tax rate must be 0–100', path: ['tax_rate'] });
  }
  const percent = parseAmount(item.discount_percent) ?? 0;
  const amount = parseAmount(item.discount_amount) ?? 0;
  if (percent > 0 && amount > 0) {
    ctx.addIssue({
      code: 'custom',
      message: 'Use percent or amount, not both',
      path: ['discount_percent'],
    });
  }
}

function refineLpoItem(item: LpoLineForm, ctx: z.RefinementCtx) {
  const hasProduct = Boolean(item.product_id?.trim());
  if (!hasProduct && !item.description?.trim()) {
    ctx.addIssue({ code: 'custom', message: 'Description required', path: ['description'] });
  }
  if (!hasProduct && parseAmount(item.unit_price) === undefined) {
    ctx.addIssue({ code: 'custom', message: 'Price required', path: ['unit_price'] });
  }
  const qty = parseAmount(item.quantity);
  if (qty === undefined || qty <= 0) {
    ctx.addIssue({ code: 'custom', message: 'Qty must be greater than 0', path: ['quantity'] });
  }
  addRateAndDiscountIssues(item, ctx);
}

const lpoItemSchema = z
  .object({
    product_id: z.string().optional(),
    description: z.string().optional(),
    quantity: z.string().min(1, 'Qty required'),
    unit_price: z.string().optional(),
    tax_rate: z.string().optional(),
    discount_percent: z.string().optional(),
    discount_amount: z.string().optional(),
  })
  .superRefine(refineLpoItem);

export const lpoSchema = z
  .object({
    client_id: z.string().min(1, 'Client required'),
    customer_po_number: z.string().optional(),
    lpo_date: z.string().min(1, 'Date required'),
    expected_delivery_date: z.string().optional(),
    notes: z.string().optional(),
    items: z.array(lpoItemSchema).min(1, 'At least one item required'),
  })
  .superRefine((data, ctx) => {
    const po = data.customer_po_number?.trim() ?? '';
    if (po.length > 100) {
      ctx.addIssue({
        code: 'custom',
        message: 'Customer PO number must be 100 characters or fewer',
        path: ['customer_po_number'],
      });
    }
    if (
      data.expected_delivery_date &&
      data.lpo_date &&
      data.expected_delivery_date < data.lpo_date
    ) {
      ctx.addIssue({
        code: 'custom',
        message: 'Expected delivery must be on or after LPO date',
        path: ['expected_delivery_date'],
      });
    }
  });

export type LpoFormValues = z.infer<typeof lpoSchema>;

export function emptyLpoLine(): LpoFormValues['items'][number] {
  return {
    product_id: '',
    description: '',
    quantity: '1',
    unit_price: '',
    tax_rate: '',
    discount_percent: '',
    discount_amount: '',
  };
}

export function blankLpoForm(): LpoFormValues {
  return {
    client_id: '',
    customer_po_number: '',
    lpo_date: todayIso(),
    expected_delivery_date: '',
    notes: '',
    items: [emptyLpoLine()],
  };
}

function lineToForm(item: LpoItem): LpoFormValues['items'][number] {
  const pct = Number(item.discount_percent ?? 0);
  const amt = Number(item.discount_amount ?? 0);
  return {
    product_id: item.product_id ?? '',
    description: item.description ?? '',
    quantity: String(item.quantity ?? 1),
    unit_price: String(item.unit_price ?? 0),
    tax_rate: item.tax_rate == null ? '' : String(item.tax_rate),
    discount_percent: pct > 0 ? String(item.discount_percent) : '',
    discount_amount: amt > 0 ? String(item.discount_amount) : '',
  };
}

export function lpoToForm(lpo: CustomerPurchaseOrder): LpoFormValues {
  return {
    client_id: lpo.client_id,
    customer_po_number: lpo.customer_po_number ?? '',
    lpo_date: lpo.lpo_date,
    expected_delivery_date: lpo.expected_delivery_date ?? '',
    notes: lpo.notes ?? '',
    items: (lpo.items ?? []).map(lineToForm),
  };
}

export function buildLpoLinePayload(item: LpoFormValues['items'][number]): LpoItemWrite {
  const line: LpoItemWrite = { quantity: Number(item.quantity) };
  const productId = item.product_id?.trim();
  if (productId) line.product_id = productId;
  const description = item.description?.trim();
  if (description) line.description = description;
  const unitPrice = parseAmount(item.unit_price);
  if (unitPrice !== undefined) line.unit_price = unitPrice;
  const taxRate = parseAmount(item.tax_rate);
  if (taxRate !== undefined) line.tax_rate = taxRate;
  const percent = parseAmount(item.discount_percent);
  if (percent && percent > 0) line.discount_percent = percent;
  const amount = parseAmount(item.discount_amount);
  if (amount && amount > 0) line.discount_amount = amount;
  return line;
}

function optionalNotes(notes?: string): string | undefined {
  const trimmed = notes?.trim();
  return trimmed || undefined;
}

export function buildLpoCreatePayload(data: LpoFormValues): LpoCreatePayload {
  const payload: LpoCreatePayload = {
    client_id: data.client_id,
    lpo_date: data.lpo_date,
    currency: 'AED',
    items: data.items.map(buildLpoLinePayload),
  };
  const po = data.customer_po_number?.trim();
  if (po) payload.customer_po_number = po;
  const delivery = data.expected_delivery_date?.trim();
  if (delivery) payload.expected_delivery_date = delivery;
  const notes = optionalNotes(data.notes);
  if (notes) payload.notes = notes;
  return payload;
}

export function buildLpoUpdatePayload(data: LpoFormValues): LpoUpdatePayload {
  const payload: LpoUpdatePayload = {
    customer_po_number: data.customer_po_number?.trim() || null,
    lpo_date: data.lpo_date,
    expected_delivery_date: data.expected_delivery_date?.trim() || null,
    currency: 'AED',
    items: data.items.map(buildLpoLinePayload),
  };
  const notes = optionalNotes(data.notes);
  if (notes) payload.notes = notes;
  return payload;
}

export function remainingQty(item: LpoItem): number {
  return Number(item.quantity_remaining ?? 0);
}
