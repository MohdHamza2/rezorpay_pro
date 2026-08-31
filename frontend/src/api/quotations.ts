import { apiClient } from './client';
import type { Invoice } from './invoices';
import type { CustomerPurchaseOrder } from './lpos';
import type { PaginatedResponse, PaginationMeta, SuccessResponse } from '../types/api';

export type QuotationStatus =
  | 'DRAFT'
  | 'SENT'
  | 'ACCEPTED'
  | 'REJECTED'
  | 'EXPIRED'
  | 'CONVERTED';

export type QuotationCurrency = 'AED';

/** Write body: only keys WP-A allows (extra="forbid"). Never hs_code / from_uom_id. */
export interface QuotationItemWrite {
  description?: string;
  quantity: number;
  unit_price?: number;
  tax_rate?: number;
  product_id?: string;
  discount_percent?: number;
  discount_amount?: number;
}

export interface QuotationItem {
  id?: string;
  quotation_id?: string;
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

export interface QuotationListItem {
  id: string;
  client_id: string;
  quotation_number: string;
  status: QuotationStatus;
  total_amount: number;
  quotation_date: string;
  valid_until: string;
  converted_invoice_id?: string | null;
  converted_lpo_id?: string | null;
  created_at?: string;
}

export interface Quotation extends QuotationListItem {
  workspace_id?: string;
  currency?: QuotationCurrency | string;
  notes?: string | null;
  rejection_reason?: string | null;
  subtotal: number;
  tax_amount: number;
  items: QuotationItem[];
  updated_at?: string;
  deleted_at?: string | null;
}

export interface QuotationCreatePayload {
  client_id: string;
  quotation_date?: string;
  valid_until?: string;
  currency?: QuotationCurrency;
  notes?: string;
  items: QuotationItemWrite[];
}

export interface QuotationUpdatePayload {
  quotation_date?: string;
  valid_until?: string;
  currency?: QuotationCurrency;
  notes?: string;
  items?: QuotationItemWrite[];
}

export interface QuotationListQuery {
  page?: number;
  per_page?: number;
  status?: QuotationStatus;
  client_id?: string;
  search?: string;
}

export interface QuotationListResult {
  items: QuotationListItem[];
  pagination: PaginationMeta;
}

function listParams(query: QuotationListQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {
    page: query.page ?? 1,
    per_page: query.per_page ?? 20,
  };
  if (query.status) params.status = query.status;
  if (query.client_id) params.client_id = query.client_id;
  if (query.search?.trim()) params.search = query.search.trim();
  return params;
}

function unwrapList(payload: PaginatedResponse<QuotationListItem>): QuotationListResult {
  const items = Array.isArray(payload.data) ? payload.data : [];
  return { items, pagination: payload.pagination };
}

export const getQuotations = async (
  query: QuotationListQuery = {},
): Promise<QuotationListResult> => {
  const response = await apiClient.get<PaginatedResponse<QuotationListItem>>(
    '/api/v1/quotations',
    { params: listParams(query) },
  );
  return unwrapList(response.data);
};

export const getQuotation = async (id: string): Promise<Quotation> => {
  const response = await apiClient.get<SuccessResponse<Quotation>>(`/api/v1/quotations/${id}`);
  return response.data.data;
};

export const createQuotation = async (data: QuotationCreatePayload): Promise<Quotation> => {
  const response = await apiClient.post<SuccessResponse<Quotation>>('/api/v1/quotations', data);
  return response.data.data;
};

export const updateQuotation = async (
  id: string,
  data: QuotationUpdatePayload,
): Promise<Quotation> => {
  const response = await apiClient.put<SuccessResponse<Quotation>>(
    `/api/v1/quotations/${id}`,
    data,
  );
  return response.data.data;
};

export const deleteQuotation = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/v1/quotations/${id}`);
};

export const sendQuotation = async (id: string): Promise<Quotation> => {
  const response = await apiClient.post<SuccessResponse<Quotation>>(
    `/api/v1/quotations/${id}/send`,
    {},
  );
  return response.data.data;
};

export const acceptQuotation = async (id: string): Promise<Quotation> => {
  const response = await apiClient.post<SuccessResponse<Quotation>>(
    `/api/v1/quotations/${id}/accept`,
  );
  return response.data.data;
};

export const rejectQuotation = async (id: string, reason?: string): Promise<Quotation> => {
  const body: { reason?: string } = {};
  if (reason) body.reason = reason;
  const response = await apiClient.post<SuccessResponse<Quotation>>(
    `/api/v1/quotations/${id}/reject`,
    body,
  );
  return response.data.data;
};

export const convertQuotationToInvoice = async (id: string): Promise<Invoice> => {
  const response = await apiClient.post<SuccessResponse<Invoice>>(
    `/api/v1/quotations/${id}/convert-to-invoice`,
  );
  return response.data.data;
};

export interface ConvertToLpoPayload {
  customer_po_number?: string;
  lpo_date?: string;
  expected_delivery_date?: string;
  notes?: string;
}

export const convertQuotationToLpo = async (
  id: string,
  data: ConvertToLpoPayload = {},
): Promise<CustomerPurchaseOrder> => {
  const body: ConvertToLpoPayload = {};
  if (data.customer_po_number?.trim()) body.customer_po_number = data.customer_po_number.trim();
  if (data.lpo_date) body.lpo_date = data.lpo_date;
  if (data.expected_delivery_date) body.expected_delivery_date = data.expected_delivery_date;
  if (data.notes?.trim()) body.notes = data.notes.trim();
  const response = await apiClient.post<SuccessResponse<CustomerPurchaseOrder>>(
    `/api/v1/quotations/${id}/convert-to-lpo`,
    body,
  );
  return response.data.data;
};
