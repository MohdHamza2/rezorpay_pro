import { apiClient } from './client';
import type { PaginatedResponse, PaginationMeta, SuccessResponse } from '../types/api';

export type TaxDebitNoteStatus = 'DRAFT' | 'ISSUED';

export type TaxDebitNoteReason =
  | 'INVOICE_ERROR'
  | 'PRICE_INCREASE'
  | 'QTY_UNDERSTATED'
  | 'ADDITIONAL_CHARGE'
  | 'OTHER';

export interface TaxDebitNoteItemWrite {
  invoice_item_id: string;
  quantity: number;
}

export interface TaxDebitNoteItem {
  id: string;
  tax_debit_note_id: string;
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

export interface TaxDebitNoteListItem {
  id: string;
  client_id: string;
  invoice_id: string;
  debit_note_number: string;
  status: TaxDebitNoteStatus;
  total_amount: number | string;
  issue_date: string;
  created_at?: string;
}

export interface TaxDebitNote extends TaxDebitNoteListItem {
  workspace_id?: string;
  currency?: string;
  reason: TaxDebitNoteReason;
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
  items: TaxDebitNoteItem[];
  updated_at?: string;
  deleted_at?: string | null;
}

export interface TaxDebitNoteCreatePayload {
  invoice_id: string;
  reason: TaxDebitNoteReason;
  reason_notes?: string;
  issue_date?: string;
  items: TaxDebitNoteItemWrite[];
}

export interface TaxDebitNoteUpdatePayload {
  reason?: TaxDebitNoteReason;
  reason_notes?: string | null;
  issue_date?: string;
  items?: TaxDebitNoteItemWrite[];
}

export interface TaxDebitNoteListQuery {
  page?: number;
  per_page?: number;
  status?: TaxDebitNoteStatus;
  client_id?: string;
  invoice_id?: string;
  search?: string;
}

export interface TaxDebitNoteListResult {
  items: TaxDebitNoteListItem[];
  pagination: PaginationMeta;
}

const BASE = '/api/v1/debit-notes';

function listParams(query: TaxDebitNoteListQuery): Record<string, string | number> {
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

function unwrapList(payload: PaginatedResponse<TaxDebitNoteListItem>): TaxDebitNoteListResult {
  const items = Array.isArray(payload.data) ? payload.data : [];
  return { items, pagination: payload.pagination };
}

function optionalText(value?: string | null): string | undefined {
  const trimmed = value?.trim();
  return trimmed || undefined;
}

function itemBody(item: TaxDebitNoteItemWrite): Record<string, unknown> {
  return { invoice_item_id: item.invoice_item_id, quantity: item.quantity };
}

export function createTaxDebitNoteBody(
  data: TaxDebitNoteCreatePayload,
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

export function updateTaxDebitNoteBody(
  data: TaxDebitNoteUpdatePayload,
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

export const getDebitNotes = async (
  query: TaxDebitNoteListQuery = {},
): Promise<TaxDebitNoteListResult> => {
  const response = await apiClient.get<PaginatedResponse<TaxDebitNoteListItem>>(BASE, {
    params: listParams(query),
  });
  return unwrapList(response.data);
};

export const getTaxDebitNote = async (id: string): Promise<TaxDebitNote> => {
  const response = await apiClient.get<SuccessResponse<TaxDebitNote>>(`${BASE}/${id}`);
  return response.data.data;
};

export const createTaxDebitNote = async (
  data: TaxDebitNoteCreatePayload,
): Promise<TaxDebitNote> => {
  const response = await apiClient.post<SuccessResponse<TaxDebitNote>>(
    BASE,
    createTaxDebitNoteBody(data),
  );
  return response.data.data;
};

export const updateTaxDebitNote = async (
  id: string,
  data: TaxDebitNoteUpdatePayload,
): Promise<TaxDebitNote> => {
  const response = await apiClient.put<SuccessResponse<TaxDebitNote>>(
    `${BASE}/${id}`,
    updateTaxDebitNoteBody(data),
  );
  return response.data.data;
};

export const deleteTaxDebitNote = async (id: string): Promise<void> => {
  await apiClient.delete(`${BASE}/${id}`);
};

export const issueTaxDebitNote = async (id: string): Promise<TaxDebitNote> => {
  const response = await apiClient.post<SuccessResponse<TaxDebitNote>>(
    `${BASE}/${id}/issue`,
    {},
  );
  return response.data.data;
};
