import { apiClient } from './client';
import type { Invoice } from './invoices';
import type { PaginatedResponse, PaginationMeta, SuccessResponse } from '../types/api';

export type LpoStatus = 'DRAFT' | 'RECEIVED' | 'PARTIAL' | 'INVOICED' | 'CANCELLED';
export type LpoCurrency = 'AED';

/** Write body: only keys WP-A allows (extra="forbid"). Never hs_code / from_uom_id. */
export interface LpoItemWrite {
  description?: string;
  quantity: number;
  unit_price?: number;
  tax_rate?: number;
  product_id?: string;
  discount_percent?: number;
  discount_amount?: number;
}

export interface LpoItem {
  id: string;
  customer_purchase_order_id?: string;
  product_id?: string | null;
  uom_id?: string | null;
  sku_snapshot?: string | null;
  description: string;
  quantity: number;
  quantity_invoiced: number;
  quantity_remaining: number;
  unit_price: number;
  tax_rate: number;
  discount_percent: number;
  discount_amount: number;
  line_net: number;
  tax_amount: number;
  total_price: number;
}

export interface LpoLinkedInvoice {
  id: string;
  invoice_number: string;
  status: string;
  total_amount: number;
}

export interface LpoListItem {
  id: string;
  client_id: string;
  lpo_number: string;
  customer_po_number?: string | null;
  status: LpoStatus;
  total_amount: number;
  lpo_date: string;
  expected_delivery_date?: string | null;
  quotation_id?: string | null;
  created_at?: string;
}

export interface CustomerPurchaseOrder extends LpoListItem {
  workspace_id?: string;
  currency?: LpoCurrency | string;
  notes?: string | null;
  cancellation_reason?: string | null;
  subtotal: number;
  tax_amount: number;
  items: LpoItem[];
  invoices?: LpoLinkedInvoice[];
  updated_at?: string;
  deleted_at?: string | null;
}

export interface LpoCreatePayload {
  client_id: string;
  customer_po_number?: string;
  lpo_date?: string;
  expected_delivery_date?: string;
  currency?: LpoCurrency;
  notes?: string;
  items: LpoItemWrite[];
}

export interface LpoUpdatePayload {
  customer_po_number?: string | null;
  lpo_date?: string;
  expected_delivery_date?: string | null;
  currency?: LpoCurrency;
  notes?: string;
  items?: LpoItemWrite[];
}

export interface LpoListQuery {
  page?: number;
  per_page?: number;
  status?: LpoStatus;
  client_id?: string;
  search?: string;
}

export interface LpoListResult {
  items: LpoListItem[];
  pagination: PaginationMeta;
}

export interface LpoInvoiceLineWrite {
  customer_purchase_order_item_id: string;
  quantity: number;
}

export interface LpoInvoiceCreatePayload {
  items?: LpoInvoiceLineWrite[];
  notes?: string;
  issue_date?: string;
  supply_date?: string;
  due_date?: string;
}

const BASE = '/api/v1/customer-purchase-orders';

function listParams(query: LpoListQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {
    page: query.page ?? 1,
    per_page: query.per_page ?? 20,
  };
  if (query.status) params.status = query.status;
  if (query.client_id) params.client_id = query.client_id;
  if (query.search?.trim()) params.search = query.search.trim();
  return params;
}

function unwrapList(payload: PaginatedResponse<LpoListItem>): LpoListResult {
  const items = Array.isArray(payload.data) ? payload.data : [];
  return { items, pagination: payload.pagination };
}

function invoiceBody(data: LpoInvoiceCreatePayload): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (data.items && data.items.length > 0) {
    body.items = data.items.map((item) => ({
      customer_purchase_order_item_id: item.customer_purchase_order_item_id,
      quantity: item.quantity,
    }));
  }
  if (data.notes?.trim()) body.notes = data.notes.trim();
  if (data.issue_date) body.issue_date = data.issue_date;
  if (data.supply_date) body.supply_date = data.supply_date;
  if (data.due_date) body.due_date = data.due_date;
  return body;
}

export const getLpos = async (query: LpoListQuery = {}): Promise<LpoListResult> => {
  const response = await apiClient.get<PaginatedResponse<LpoListItem>>(BASE, {
    params: listParams(query),
  });
  return unwrapList(response.data);
};

export const getLpo = async (id: string): Promise<CustomerPurchaseOrder> => {
  const response = await apiClient.get<SuccessResponse<CustomerPurchaseOrder>>(`${BASE}/${id}`);
  return response.data.data;
};

export const createLpo = async (data: LpoCreatePayload): Promise<CustomerPurchaseOrder> => {
  const response = await apiClient.post<SuccessResponse<CustomerPurchaseOrder>>(BASE, data);
  return response.data.data;
};

export const updateLpo = async (
  id: string,
  data: LpoUpdatePayload,
): Promise<CustomerPurchaseOrder> => {
  const response = await apiClient.put<SuccessResponse<CustomerPurchaseOrder>>(
    `${BASE}/${id}`,
    data,
  );
  return response.data.data;
};

export const deleteLpo = async (id: string): Promise<void> => {
  await apiClient.delete(`${BASE}/${id}`);
};

export const receiveLpo = async (id: string): Promise<CustomerPurchaseOrder> => {
  const response = await apiClient.post<SuccessResponse<CustomerPurchaseOrder>>(
    `${BASE}/${id}/receive`,
    {},
  );
  return response.data.data;
};

export const cancelLpo = async (id: string, reason?: string): Promise<CustomerPurchaseOrder> => {
  const body: { reason?: string } = {};
  if (reason) body.reason = reason;
  const response = await apiClient.post<SuccessResponse<CustomerPurchaseOrder>>(
    `${BASE}/${id}/cancel`,
    body,
  );
  return response.data.data;
};

export const createLpoInvoice = async (
  id: string,
  data: LpoInvoiceCreatePayload = {},
): Promise<Invoice> => {
  const response = await apiClient.post<SuccessResponse<Invoice>>(
    `${BASE}/${id}/invoices`,
    invoiceBody(data),
  );
  return response.data.data;
};
