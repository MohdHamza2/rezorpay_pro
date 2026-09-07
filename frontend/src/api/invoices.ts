import { apiClient } from './client';
import type { PaginatedResponse, SuccessResponse } from '../types/api';

export type InvoiceStatus =
  | 'DRAFT'
  | 'SENT'
  | 'PARTIALLY_PAID'
  | 'OVERDUE'
  | 'PAID'
  | 'CANCELLED';
export type InvoiceKind = 'STANDARD' | 'SIMPLIFIED';
export type InvoiceCurrency = 'AED';

export interface InvoiceItem {
  id?: string;
  invoice_id?: string;
  product_id?: string | null;
  uom_id?: string | null;
  sku_snapshot?: string | null;
  description: string;
  quantity: number;
  unit_price: number;
  tax_rate: number;
  discount_percent: number;
  discount_amount: number;
  line_net: number;
  tax_amount: number;
  total_price: number;
}

/** Write body: only keys WP-A allows (extra="forbid"). Never hs_code / from_uom_id. */
export interface InvoiceItemWrite {
  description?: string;
  quantity: number;
  unit_price?: number;
  tax_rate?: number;
  product_id?: string;
  discount_percent?: number;
  discount_amount?: number;
}

export interface InvoiceListItem {
  id: string;
  client_id: string;
  invoice_number: string;
  status: InvoiceStatus;
  total_amount: number;
  amount_paid: number;
  amount_credited?: number | string | null;
  amount_debited?: number | string | null;
  balance_due: number;
  issue_date: string;
  due_date: string;
  created_at?: string;
}

export interface Invoice extends InvoiceListItem {
  supply_date: string;
  customer_purchase_order_id?: string | null;
  quotation_id?: string | null;
  currency?: InvoiceCurrency | string;
  invoice_kind?: InvoiceKind | null;
  seller_trn_snapshot?: string | null;
  seller_name_snapshot?: string | null;
  seller_address_snapshot?: string | null;
  buyer_trn_snapshot?: string | null;
  buyer_name_snapshot?: string | null;
  buyer_address_snapshot?: string | null;
  subtotal: number;
  tax_amount: number;
  items: InvoiceItem[];
}

export interface InvoiceCreatePayload {
  client_id: string;
  issue_date: string;
  due_date: string;
  supply_date?: string;
  currency?: InvoiceCurrency;
  items: InvoiceItemWrite[];
}

export interface InvoiceUpdatePayload {
  issue_date?: string;
  due_date?: string;
  supply_date?: string;
  currency?: InvoiceCurrency;
  items?: InvoiceItemWrite[];
}

export const getInvoices = async (): Promise<InvoiceListItem[]> => {
  const response = await apiClient.get<PaginatedResponse<InvoiceListItem>>('/api/v1/invoices', {
    params: { page: 1, per_page: 100 },
  });
  return response.data.data;
};

export const getRecentInvoices = async (): Promise<InvoiceListItem[]> => {
  const response = await apiClient.get<PaginatedResponse<InvoiceListItem>>('/api/v1/invoices', {
    params: { page: 1, per_page: 5 },
  });
  return response.data.data;
};

export const getInvoice = async (id: string): Promise<Invoice> => {
  const response = await apiClient.get<SuccessResponse<Invoice>>('/api/v1/invoices/' + id);
  return response.data.data;
};

export const createInvoice = async (data: InvoiceCreatePayload): Promise<Invoice> => {
  const response = await apiClient.post<SuccessResponse<Invoice>>('/api/v1/invoices', data);
  return response.data.data;
};

export const updateInvoice = async (id: string, data: InvoiceUpdatePayload): Promise<Invoice> => {
  const response = await apiClient.put<SuccessResponse<Invoice>>('/api/v1/invoices/' + id, data);
  return response.data.data;
};

export const sendInvoice = async (id: string): Promise<Invoice> => {
  const response = await apiClient.post<SuccessResponse<Invoice>>('/api/v1/invoices/' + id + '/send', {});
  return response.data.data;
};

export const voidInvoice = async (id: string, reason: string): Promise<Invoice> => {
  const response = await apiClient.post<SuccessResponse<Invoice>>('/api/v1/invoices/' + id + '/void', { reason });
  return response.data.data;
};

export type PaymentMethod = 'CASH' | 'BANK_TRANSFER' | 'CREDIT_CARD' | 'CHEQUE' | 'PDC';
export type PaymentStatus = 'PENDING' | 'SUCCESS' | 'FAILED' | 'CANCELLED' | 'REFUNDED';
export type PdcStatus = 'RECEIVED' | 'DEPOSITED' | 'CLEARED' | 'BOUNCED' | 'RETURNED';
export type PdcAction = 'deposit' | 'clear' | 'bounce' | 'return';

export interface Payment {
  id: string;
  invoice_id: string;
  amount: number | string;
  payment_method: PaymentMethod | string;
  payment_date?: string;
  status: PaymentStatus | string;
  reference_number?: string | null;
  bank_name?: string | null;
  pdc_date?: string | null;
  pdc_status?: PdcStatus | string | null;
  created_at?: string;
  updated_at?: string;
}

/** Write body: only keys WP-A allows. Never send pdc_status. */
export interface PaymentData {
  amount: number;
  payment_method: PaymentMethod | string;
  payment_date?: string;
  reference_number?: string;
  bank_name?: string;
  pdc_date?: string;
}

function optionalText(value?: string | null): string | undefined {
  const trimmed = value?.trim();
  return trimmed || undefined;
}

export function paymentCreateBody(data: PaymentData): Record<string, unknown> {
  const body: Record<string, unknown> = {
    amount: data.amount,
    payment_method: data.payment_method,
  };
  if (data.payment_date) body.payment_date = data.payment_date;
  const reference = optionalText(data.reference_number);
  if (reference) body.reference_number = reference;
  const bank = optionalText(data.bank_name);
  if (bank) body.bank_name = bank;
  if (data.payment_method === 'PDC' && data.pdc_date) body.pdc_date = data.pdc_date;
  return body;
}

export const recordPayment = async (id: string, data: PaymentData): Promise<Payment> => {
  const idempotencyKey = crypto.randomUUID();
  const response = await apiClient.post<SuccessResponse<Payment>>(
    '/api/v1/invoices/' + id + '/payments',
    paymentCreateBody(data),
    { headers: { 'Idempotency-Key': idempotencyKey } },
  );
  return response.data.data;
};

export const listPayments = async (invoiceId: string): Promise<Payment[]> => {
  const response = await apiClient.get<PaginatedResponse<Payment>>(
    `/api/v1/invoices/${invoiceId}/payments`,
    { params: { page: 1, per_page: 100 } },
  );
  return Array.isArray(response.data.data) ? response.data.data : [];
};

export const postPdcAction = async (
  invoiceId: string,
  paymentId: string,
  action: PdcAction,
): Promise<Payment> => {
  const response = await apiClient.post<SuccessResponse<Payment>>(
    `/api/v1/invoices/${invoiceId}/payments/${paymentId}/pdc/${action}`,
    {},
  );
  return response.data.data;
};
