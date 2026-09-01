import { apiClient } from './client';
import type { PaginatedResponse, PaginationMeta, SuccessResponse } from '../types/api';

export type CreditNoteStatus = 'DRAFT' | 'ISSUED';

export type CreditNoteReason =
  | 'SALES_RETURN'
  | 'INVOICE_ERROR'
  | 'DISCOUNT'
  | 'GOODWILL'
  | 'OTHER';

export interface CreditNoteItemWrite {
  invoice_item_id: string;
  quantity: number;
}

export interface CreditNoteItem {
  id: string;
  credit_note_id: string;
  invoice_item_id: string;
  product_id?: string | null;
  uom_id?: string | null;
  sku_snapshot?: string | null;
  description: string;
  quantity: number | string;
  unit_price: number | string;
  tax_rate: number | string;
  discount_percent: number | string;
  discount_amount: number | string;
  line_net: number | string;
  tax_amount: number | string;
  total_price: number | string;
  created_at?: string;
  updated_at?: string;
}

export interface CreditNoteListItem {
  id: string;
  client_id: string;
  invoice_id: string;
  credit_note_number: string;
  status: CreditNoteStatus;
  total_amount: number | string;
  issue_date: string;
  created_at?: string;
}

export interface CreditNote extends CreditNoteListItem {
  workspace_id?: string;
  currency?: string;
  reason: CreditNoteReason;
  reason_notes?: string | null;
  subtotal: number | string;
  tax_amount: number | string;
  original_invoice_number?: string | null;
  original_issue_date?: string | null;
  invoice_kind?: string | null;
  seller_trn_snapshot?: string | null;
  seller_name_snapshot?: string | null;
  seller_address_snapshot?: string | null;
  buyer_trn_snapshot?: string | null;
  buyer_name_snapshot?: string | null;
  buyer_address_snapshot?: string | null;
  items: CreditNoteItem[];
  updated_at?: string;
  deleted_at?: string | null;
}

export interface CreditNoteCreatePayload {
  invoice_id: string;
  reason: CreditNoteReason;
  reason_notes?: string;
  issue_date?: string;
  items: CreditNoteItemWrite[];
}

export interface CreditNoteUpdatePayload {
  reason?: CreditNoteReason;
  reason_notes?: string | null;
  issue_date?: string;
  items?: CreditNoteItemWrite[];
}

export interface CreditNoteListQuery {
  page?: number;
  per_page?: number;
  status?: CreditNoteStatus;
  client_id?: string;
  invoice_id?: string;
  search?: string;
}

export interface CreditNoteListResult {
  items: CreditNoteListItem[];
  pagination: PaginationMeta;
}

const BASE = '/api/v1/credit-notes';

function listParams(query: CreditNoteListQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {
    page: query.page ?? 1,
    per_page: query.per_page ?? 20,
  };
  if (query.status) params.status = query.status;
  if (query.client_id) params.client_id = query.client_id;
  if (query.invoice_id) params.invoice_id = query.invoice_id;
  if (query.search?.trim()) params.search = query.search.trim();
  return params;
}

function unwrapList(payload: PaginatedResponse<CreditNoteListItem>): CreditNoteListResult {
  const items = Array.isArray(payload.data) ? payload.data : [];
  return { items, pagination: payload.pagination };
}

function optionalText(value?: string | null): string | undefined {
  const trimmed = value?.trim();
  return trimmed || undefined;
}

function itemBody(item: CreditNoteItemWrite): Record<string, unknown> {
  return { invoice_item_id: item.invoice_item_id, quantity: item.quantity };
}

export function createCreditNoteBody(
  data: CreditNoteCreatePayload,
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    invoice_id: data.invoice_id,
    reason: data.reason,
    items: data.items.map(itemBody),
  };
  const notes = optionalText(data.reason_notes);
  if (notes) body.reason_notes = notes;
  if (data.issue_date) body.issue_date = data.issue_date;
  return body;
}

export function updateCreditNoteBody(
  data: CreditNoteUpdatePayload,
): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (data.reason) body.reason = data.reason;
  if (data.reason_notes !== undefined) {
    body.reason_notes = optionalText(data.reason_notes) ?? null;
  }
  if (data.issue_date) body.issue_date = data.issue_date;
  if (data.items && data.items.length > 0) {
    body.items = data.items.map(itemBody);
  }
  return body;
}

export const getCreditNotes = async (
  query: CreditNoteListQuery = {},
): Promise<CreditNoteListResult> => {
  const response = await apiClient.get<PaginatedResponse<CreditNoteListItem>>(BASE, {
    params: listParams(query),
  });
  return unwrapList(response.data);
};

export const getCreditNote = async (id: string): Promise<CreditNote> => {
  const response = await apiClient.get<SuccessResponse<CreditNote>>(`${BASE}/${id}`);
  return response.data.data;
};

export const createCreditNote = async (
  data: CreditNoteCreatePayload,
): Promise<CreditNote> => {
  const response = await apiClient.post<SuccessResponse<CreditNote>>(
    BASE,
    createCreditNoteBody(data),
  );
  return response.data.data;
};

export const updateCreditNote = async (
  id: string,
  data: CreditNoteUpdatePayload,
): Promise<CreditNote> => {
  const response = await apiClient.put<SuccessResponse<CreditNote>>(
    `${BASE}/${id}`,
    updateCreditNoteBody(data),
  );
  return response.data.data;
};

export const deleteCreditNote = async (id: string): Promise<void> => {
  await apiClient.delete(`${BASE}/${id}`);
};

export const issueCreditNote = async (id: string): Promise<CreditNote> => {
  const response = await apiClient.post<SuccessResponse<CreditNote>>(
    `${BASE}/${id}/issue`,
    {},
  );
  return response.data.data;
};
