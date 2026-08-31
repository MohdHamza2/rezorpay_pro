import { apiClient } from './client';
import type { PaginatedResponse, SuccessResponse } from '../types/api';

export type InvoiceStatus = 'DRAFT' | 'SENT' | 'PARTIALLY_PAID' | 'PAID' | 'CANCELLED';
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

export interface PaymentData {
  amount: number;
  payment_method: string;
  payment_date?: string;
  reference_number?: string;
  bank_name?: string;
  pdc_date?: string;
  pdc_status?: string;
}

export const recordPayment = async (id: string, data: PaymentData): Promise<unknown> => {
  const idempotencyKey = crypto.randomUUID();
  const response = await apiClient.post<SuccessResponse<unknown>>(
    '/api/v1/invoices/' + id + '/payments',
    data,
    { headers: { 'Idempotency-Key': idempotencyKey } }
  );
  return response.data.data;
};
