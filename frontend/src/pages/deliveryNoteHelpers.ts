import { z } from 'zod';
import { getInvoice } from '../api/invoices';
import type { Invoice, InvoiceItem } from '../api/invoices';
import { getDeliveryNote, getDeliveryNotes } from '../api/deliveryNotes';
import type {
  DeliveryNote,
  DeliveryNoteCreatePayload,
  DeliveryNoteItemWrite,
  DeliveryNoteUpdatePayload,
} from '../api/deliveryNotes';
import type { CustomerPurchaseOrder, LpoItem } from '../api/lpos';
import { parseAmount, todayIso } from './quotationHelpers';

export type DnParentKind = 'lpo' | 'invoice';

export type DnLineForm = {
  parent_item_id: string;
  description: string;
  sku: string;
  ordered: string;
  delivered: string;
  remaining: string;
  quantity: string;
};

export function formatQty(value: string | number | null | undefined): string {
  return Number(value ?? 0).toFixed(2);
}

export function undeliveredQty(item: LpoItem): number {
  if (item.quantity_undelivered != null) {
    return Number(item.quantity_undelivered ?? 0);
  }
  const ordered = Number(item.quantity ?? 0);
  const delivered = Number(item.quantity_delivered ?? 0);
  return Math.max(0, ordered - delivered);
}

function refineQty(item: DnLineForm, ctx: z.RefinementCtx) {
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
  }
}

const dnItemSchema = z
  .object({
    parent_item_id: z.string().min(1),
    description: z.string(),
    sku: z.string(),
    ordered: z.string(),
    delivered: z.string(),
    remaining: z.string(),
    quantity: z.string(),
  })
  .superRefine(refineQty);

export const deliveryNoteSchema = z
  .object({
    parent_kind: z.enum(['lpo', 'invoice']),
    customer_purchase_order_id: z.string().optional(),
    invoice_id: z.string().optional(),
    warehouse_id: z.string().min(1, 'Warehouse required'),
    bin_id: z.string().optional(),
    delivery_date: z.string().min(1, 'Delivery date required'),
    shipping_address: z.string().optional(),
    vehicle_number: z.string().optional(),
    driver_name: z.string().optional(),
    notes: z.string().optional(),
    items: z.array(dnItemSchema),
  })
  .superRefine((data, ctx) => {
    if (data.parent_kind === 'lpo' && !data.customer_purchase_order_id) {
      ctx.addIssue({ code: 'custom', message: 'LPO required', path: ['customer_purchase_order_id'] });
    }
    if (data.parent_kind === 'invoice' && !data.invoice_id) {
      ctx.addIssue({ code: 'custom', message: 'Invoice required', path: ['invoice_id'] });
    }
    const selected = data.items.filter((item) => (parseAmount(item.quantity) ?? 0) > 0);
    if (selected.length === 0) {
      ctx.addIssue({
        code: 'custom',
        message: 'Enter quantity on at least one remaining line',
        path: ['items'],
      });
    }
  });

export type DeliveryNoteFormValues = z.infer<typeof deliveryNoteSchema>;

export function blankDeliveryNoteForm(): DeliveryNoteFormValues {
  return {
    parent_kind: 'lpo',
    customer_purchase_order_id: '',
    invoice_id: '',
    warehouse_id: '',
    bin_id: '',
    delivery_date: todayIso(),
    shipping_address: '',
    vehicle_number: '',
    driver_name: '',
    notes: '',
    items: [],
  };
}

export function lpoItemToLine(item: LpoItem): DnLineForm {
  const remaining = undeliveredQty(item);
  const delivered = Number(item.quantity_delivered ?? 0);
  return {
    parent_item_id: item.id,
    description: item.description,
    sku: item.sku_snapshot ?? '',
    ordered: String(item.quantity ?? 0),
    delivered: String(delivered),
    remaining: String(remaining),
    quantity: remaining > 0 ? String(remaining) : '0',
  };
}

export function remainingLpoLines(lpo: CustomerPurchaseOrder): DnLineForm[] {
  return (lpo.items ?? []).map(lpoItemToLine).filter((line) => Number(line.remaining ?? 0) > 0);
}

function invoiceItemToLine(item: InvoiceItem, delivered: number): DnLineForm {
  const ordered = Number(item.quantity ?? 0);
  const remaining = Math.max(0, ordered - delivered);
  return {
    parent_item_id: item.id ?? '',
    description: item.description,
    sku: item.sku_snapshot ?? '',
    ordered: String(ordered),
    delivered: String(delivered),
    remaining: String(remaining),
    quantity: remaining > 0 ? String(remaining) : '0',
  };
}

export function remainingInvoiceLines(
  invoice: Invoice,
  delivered: Record<string, number>,
): DnLineForm[] {
  return (invoice.items ?? [])
    .map((item) => invoiceItemToLine(item, delivered[item.id ?? ''] ?? 0))
    .filter((line) => line.parent_item_id && Number(line.remaining ?? 0) > 0);
}

export async function confirmedInvoiceQtyMap(
  invoiceId: string,
): Promise<Record<string, number>> {
  const listed = await getDeliveryNotes({
    invoice_id: invoiceId,
    status: 'CONFIRMED',
    per_page: 100,
  });
  const details = await Promise.all(listed.items.map((row) => getDeliveryNote(row.id)));
  const map: Record<string, number> = {};
  for (const dn of details) {
    for (const item of dn.items ?? []) {
      const key = item.invoice_item_id;
      if (!key) continue;
      map[key] = (map[key] ?? 0) + Number(item.quantity ?? 0);
    }
  }
  return map;
}

export async function loadInvoiceRemainingLines(invoiceId: string): Promise<DnLineForm[]> {
  const invoice = await getInvoice(invoiceId);
  const delivered = await confirmedInvoiceQtyMap(invoiceId);
  return remainingInvoiceLines(invoice, delivered);
}

function qtyByParent(dn: DeliveryNote): Record<string, number> {
  const map: Record<string, number> = {};
  for (const item of dn.items ?? []) {
    const key = item.customer_purchase_order_item_id || item.invoice_item_id;
    if (!key) continue;
    map[key] = Number(item.quantity ?? 0);
  }
  return map;
}

export function applyDraftQtys(lines: DnLineForm[], dn: DeliveryNote): DnLineForm[] {
  const current = qtyByParent(dn);
  return lines.map((line) => {
    const qty = current[line.parent_item_id];
    return qty == null ? line : { ...line, quantity: String(qty) };
  });
}

function lineWrites(
  items: DnLineForm[],
  kind: DnParentKind,
): DeliveryNoteItemWrite[] {
  const writes: DeliveryNoteItemWrite[] = [];
  for (const item of items) {
    const qty = parseAmount(item.quantity);
    if (qty === undefined || qty <= 0) continue;
    if (kind === 'lpo') {
      writes.push({ customer_purchase_order_item_id: item.parent_item_id, quantity: qty });
    } else {
      writes.push({ invoice_item_id: item.parent_item_id, quantity: qty });
    }
  }
  return writes;
}

function optionalNotes(notes?: string): string | undefined {
  const trimmed = notes?.trim();
  return trimmed || undefined;
}

export function buildDnCreatePayload(data: DeliveryNoteFormValues): DeliveryNoteCreatePayload {
  const kind = data.parent_kind;
  const payload: DeliveryNoteCreatePayload = {
    warehouse_id: data.warehouse_id,
    delivery_date: data.delivery_date,
    items: lineWrites(data.items, kind),
  };
  if (kind === 'lpo') payload.customer_purchase_order_id = data.customer_purchase_order_id;
  if (kind === 'invoice') payload.invoice_id = data.invoice_id;
  const bin = data.bin_id?.trim();
  if (bin) payload.bin_id = bin;
  const address = optionalNotes(data.shipping_address);
  if (address) payload.shipping_address = address;
  const vehicle = optionalNotes(data.vehicle_number);
  if (vehicle) payload.vehicle_number = vehicle;
  const driver = optionalNotes(data.driver_name);
  if (driver) payload.driver_name = driver;
  const notes = optionalNotes(data.notes);
  if (notes) payload.notes = notes;
  return payload;
}

export function buildDnUpdatePayload(data: DeliveryNoteFormValues): DeliveryNoteUpdatePayload {
  const payload: DeliveryNoteUpdatePayload = {
    warehouse_id: data.warehouse_id,
    delivery_date: data.delivery_date,
    shipping_address: data.shipping_address?.trim() || null,
    vehicle_number: data.vehicle_number?.trim() || null,
    driver_name: data.driver_name?.trim() || null,
    items: lineWrites(data.items, data.parent_kind),
  };
  const bin = data.bin_id?.trim();
  if (bin) payload.bin_id = bin;
  const notes = optionalNotes(data.notes);
  if (notes) payload.notes = notes;
  return payload;
}

export function dnToForm(dn: DeliveryNote): DeliveryNoteFormValues {
  const kind: DnParentKind = dn.customer_purchase_order_id ? 'lpo' : 'invoice';
  return {
    parent_kind: kind,
    customer_purchase_order_id: dn.customer_purchase_order_id ?? '',
    invoice_id: dn.invoice_id ?? '',
    warehouse_id: dn.warehouse_id,
    bin_id: dn.bin_id ?? '',
    delivery_date: dn.delivery_date,
    shipping_address: dn.shipping_address ?? '',
    vehicle_number: dn.vehicle_number ?? '',
    driver_name: dn.driver_name ?? '',
    notes: dn.notes ?? '',
    items: (dn.items ?? []).map((item) => ({
      parent_item_id: item.customer_purchase_order_item_id || item.invoice_item_id || '',
      description: item.description,
      sku: item.sku_snapshot ?? '',
      ordered: String(item.quantity ?? 0),
      delivered: '0',
      remaining: String(item.quantity ?? 0),
      quantity: String(item.quantity ?? 0),
    })),
  };
}
