import { z } from 'zod';
import type {
  Quotation,
  QuotationCreatePayload,
  QuotationItem,
  QuotationItemWrite,
  QuotationUpdatePayload,
} from '../api/quotations';

export type LineForm = {
  product_id?: string;
  description?: string;
  quantity: string;
  unit_price?: string;
  tax_rate?: string;
  discount_percent?: string;
  discount_amount?: string;
};

export function parseAmount(value: string | undefined): number | undefined {
  if (value == null || value.trim() === '') return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function todayIso(): string {
  return new Date().toISOString().split('T')[0];
}

export function plusDaysIso(days: number): string {
  const ms = Date.now() + days * 24 * 60 * 60 * 1000;
  return new Date(ms).toISOString().split('T')[0];
}

export function formatAed(value: string | number | null | undefined): string {
  return `AED ${Number(value ?? 0).toFixed(2)}`;
}

function addRateAndDiscountIssues(item: LineForm, ctx: z.RefinementCtx) {
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

function refineQuotationItem(item: LineForm, ctx: z.RefinementCtx) {
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

const quotationItemSchema = z
  .object({
    product_id: z.string().optional(),
    description: z.string().optional(),
    quantity: z.string().min(1, 'Qty required'),
    unit_price: z.string().optional(),
    tax_rate: z.string().optional(),
    discount_percent: z.string().optional(),
    discount_amount: z.string().optional(),
  })
  .superRefine(refineQuotationItem);

export const quotationSchema = z
  .object({
    client_id: z.string().min(1, 'Client required'),
    quotation_date: z.string().min(1, 'Date required'),
    valid_until: z.string().min(1, 'Valid until required'),
    notes: z.string().optional(),
    items: z.array(quotationItemSchema).min(1, 'At least one item required'),
  })
  .superRefine((data, ctx) => {
    if (data.valid_until && data.quotation_date && data.valid_until < data.quotation_date) {
      ctx.addIssue({
        code: 'custom',
        message: 'Valid until must be on or after quotation date',
        path: ['valid_until'],
      });
    }
  });

export type QuotationFormValues = z.infer<typeof quotationSchema>;

export function emptyLine(): QuotationFormValues['items'][number] {
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

export function blankQuotationForm(): QuotationFormValues {
  const quotationDate = todayIso();
  return {
    client_id: '',
    quotation_date: quotationDate,
    valid_until: plusDaysIso(14),
    notes: '',
    items: [emptyLine()],
  };
}

function lineToForm(item: QuotationItem): QuotationFormValues['items'][number] {
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

export function quoteToForm(quote: Quotation): QuotationFormValues {
  return {
    client_id: quote.client_id,
    quotation_date: quote.quotation_date,
    valid_until: quote.valid_until,
    notes: quote.notes ?? '',
    items: (quote.items ?? []).map(lineToForm),
  };
}

export function buildLinePayload(item: QuotationFormValues['items'][number]): QuotationItemWrite {
  const line: QuotationItemWrite = { quantity: Number(item.quantity) };
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

export function buildCreatePayload(data: QuotationFormValues): QuotationCreatePayload {
  const payload: QuotationCreatePayload = {
    client_id: data.client_id,
    quotation_date: data.quotation_date,
    valid_until: data.valid_until,
    currency: 'AED',
    items: data.items.map(buildLinePayload),
  };
  const notes = data.notes?.trim();
  if (notes) payload.notes = notes;
  return payload;
}

export function buildUpdatePayload(data: QuotationFormValues): QuotationUpdatePayload {
  const payload: QuotationUpdatePayload = {
    quotation_date: data.quotation_date,
    valid_until: data.valid_until,
    currency: 'AED',
    items: data.items.map(buildLinePayload),
  };
  const notes = data.notes?.trim();
  if (notes) payload.notes = notes;
  return payload;
}
