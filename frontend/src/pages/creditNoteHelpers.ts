import { z } from 'zod';
import { getInvoice } from '../api/invoices';
import type { Invoice, InvoiceItem, InvoiceStatus } from '../api/invoices';
import { getCreditNote, getCreditNotes } from '../api/creditNotes';
import type {
  CreditNote,
  CreditNoteCreatePayload,
  CreditNoteItemWrite,
  CreditNoteReason,
  CreditNoteUpdatePayload,
} from '../api/creditNotes';
import { parseAmount, todayIso } from './quotationHelpers';

export const CREDITABLE_STATUSES: ReadonlySet<InvoiceStatus> = new Set([
  'SENT',
  'PARTIALLY_PAID',
  'PAID',
  'OVERDUE',
]);

export const CREDIT_NOTE_REASONS: CreditNoteReason[] = [
  'SALES_RETURN',
  'INVOICE_ERROR',
  'DISCOUNT',
  'GOODWILL',
  'OTHER',
];

export const REASON_LABELS: Record<CreditNoteReason, string> = {
  SALES_RETURN: 'Sales return',
  INVOICE_ERROR: 'Invoice error',
  DISCOUNT: 'Discount',
  GOODWILL: 'Goodwill',
  OTHER: 'Other',
};

export type CnLineForm = {
  invoice_item_id: string;
  description: string;
  sku: string;
  ordered: string;
  credited: string;
  remaining: string;
  quantity: string;
  has_amount_discount?: boolean;
};

export function formatQty(value: string | number | null | undefined): string {
  return Number(value ?? 0).toFixed(2);
}

export function isCreditableStatus(status: InvoiceStatus): boolean {
  return CREDITABLE_STATUSES.has(status);
}

function refineQty(item: CnLineForm, ctx: z.RefinementCtx) {
  const raw = item.quantity?.trim() ?? '';
  if (raw === '' || raw === '0') return;
  const qty = parseAmount(item.quantity);
  const remaining = Number(item.remaining ?? 0);
  if (qty === undefined || qty <= 0) {
    ctx.addIssue({ code: 'custom', message: 'Qty must be greater than 0', path: ['quantity'] });
  } else if (qty > remaining) {
    ctx.addIssue({
      code: 'custom',
      message: `Cannot exceed remaining (${formatQty(remaining)})`,
      path: ['quantity'],
    });
  } else if (item.has_amount_discount && qty !== remaining) {
    ctx.addIssue({
      code: 'custom',
      message: 'Amount-discount lines must credit remaining qty in full',
      path: ['quantity'],
    });
  }
}

const cnItemSchema = z
  .object({
    invoice_item_id: z.string().min(1),
    description: z.string(),
    sku: z.string(),
    ordered: z.string(),
    credited: z.string(),
    remaining: z.string(),
    quantity: z.string(),
    has_amount_discount: z.boolean().optional(),
  })
  .superRefine(refineQty);

export const creditNoteSchema = z
  .object({
    invoice_id: z.string().min(1, 'Invoice required'),
    reason: z.enum([
      'SALES_RETURN',
      'INVOICE_ERROR',
      'DISCOUNT',
      'GOODWILL',
      'OTHER',
    ]),
    reason_notes: z.string().optional(),
    issue_date: z.string().min(1, 'Issue date required'),
    items: z.array(cnItemSchema),
  })
  .superRefine((data, ctx) => {
    const selected = data.items.filter((item) => (parseAmount(item.quantity) ?? 0) > 0);
    if (selected.length === 0) {
      ctx.addIssue({
        code: 'custom',
        message: 'Enter quantity on at least one remaining line',
        path: ['items'],
      });
    }
  });

export type CreditNoteFormValues = z.infer<typeof creditNoteSchema>;

export function blankCreditNoteForm(invoiceId = ''): CreditNoteFormValues {
  return {
    invoice_id: invoiceId,
    reason: 'SALES_RETURN',
    reason_notes: '',
    issue_date: todayIso(),
    items: [],
  };
}

function hasAmountDiscount(item: InvoiceItem): boolean {
  return Number(item.discount_amount ?? 0) > 0;
}

function invoiceItemToLine(item: InvoiceItem, credited: number): CnLineForm {
  const ordered = Number(item.quantity ?? 0);
  const remaining = Math.max(0, ordered - credited);
  const amountDiscount = hasAmountDiscount(item);
  return {
    invoice_item_id: item.id ?? '',
    description: item.description,
    sku: item.sku_snapshot ?? '',
    ordered: String(ordered),
    credited: String(credited),
    remaining: String(remaining),
    quantity: remaining > 0 ? String(remaining) : '0',
    has_amount_discount: amountDiscount,
  };
}

export function remainingInvoiceLines(
  invoice: Invoice,
  credited: Record<string, number>,
): CnLineForm[] {
  return (invoice.items ?? [])
    .map((item) => invoiceItemToLine(item, credited[item.id ?? ''] ?? 0))
    .filter((line) => line.invoice_item_id && Number(line.remaining ?? 0) > 0);
}

export async function issuedCreditQtyMap(
  invoiceId: string,
): Promise<Record<string, number>> {
  const listed = await getCreditNotes({
    invoice_id: invoiceId,
    status: 'ISSUED',
    per_page: 100,
  });
  const details = await Promise.all(listed.items.map((row) => getCreditNote(row.id)));
  const map: Record<string, number> = {};
  for (const cn of details) {
    for (const item of cn.items ?? []) {
      const key = item.invoice_item_id;
      if (!key) continue;
      map[key] = (map[key] ?? 0) + Number(item.quantity ?? 0);
    }
  }
  return map;
}

export async function loadCreditRemainingLines(invoiceId: string): Promise<CnLineForm[]> {
  const invoice = await getInvoice(invoiceId);
  const credited = await issuedCreditQtyMap(invoiceId);
  return remainingInvoiceLines(invoice, credited);
}

function qtyByItem(cn: CreditNote): Record<string, number> {
  const map: Record<string, number> = {};
  for (const item of cn.items ?? []) {
    map[item.invoice_item_id] = Number(item.quantity ?? 0);
  }
  return map;
}

export function applyDraftQtys(lines: CnLineForm[], cn: CreditNote): CnLineForm[] {
  const current = qtyByItem(cn);
  return lines.map((line) => {
    const qty = current[line.invoice_item_id];
    return qty == null ? line : { ...line, quantity: String(qty) };
  });
}

function lineWrites(items: CreditNoteFormValues['items']): CreditNoteItemWrite[] {
  const writes: CreditNoteItemWrite[] = [];
  for (const item of items) {
    const qty = parseAmount(item.quantity);
    if (qty === undefined || qty <= 0) continue;
    writes.push({ invoice_item_id: item.invoice_item_id, quantity: qty });
  }
  return writes;
}

function optionalNotes(notes?: string): string | undefined {
  const trimmed = notes?.trim();
  return trimmed || undefined;
}

export function buildCnCreatePayload(data: CreditNoteFormValues): CreditNoteCreatePayload {
  const payload: CreditNoteCreatePayload = {
    invoice_id: data.invoice_id,
    reason: data.reason,
    issue_date: data.issue_date,
    items: lineWrites(data.items),
  };
  const notes = optionalNotes(data.reason_notes);
  if (notes) payload.reason_notes = notes;
  return payload;
}

export function buildCnUpdatePayload(data: CreditNoteFormValues): CreditNoteUpdatePayload {
  const payload: CreditNoteUpdatePayload = {
    reason: data.reason,
    issue_date: data.issue_date,
    items: lineWrites(data.items),
  };
  payload.reason_notes = optionalNotes(data.reason_notes) ?? null;
  return payload;
}

export function cnToForm(cn: CreditNote): CreditNoteFormValues {
  return {
    invoice_id: cn.invoice_id,
    reason: cn.reason,
    reason_notes: cn.reason_notes ?? '',
    issue_date: cn.issue_date,
    items: (cn.items ?? []).map((item) => ({
      invoice_item_id: item.invoice_item_id,
      description: item.description,
      sku: item.sku_snapshot ?? '',
      ordered: String(item.quantity ?? 0),
      credited: '0',
      remaining: String(item.quantity ?? 0),
      quantity: String(item.quantity ?? 0),
      has_amount_discount: Number(item.discount_amount ?? 0) > 0,
    })),
  };
}
