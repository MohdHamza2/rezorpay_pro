import { apiClient } from './client';
import type { PaginatedResponse, PaginationMeta, SuccessResponse } from '../types/api';

export type DeliveryNoteStatus = 'DRAFT' | 'CONFIRMED' | 'CANCELLED';

export interface DeliveryNoteItemWrite {
  customer_purchase_order_item_id?: string;
  invoice_item_id?: string;
  quantity: number;
  bin_id?: string;
}

export interface DeliveryNoteItem {
  id: string;
  delivery_note_id: string;
  customer_purchase_order_item_id?: string | null;
  invoice_item_id?: string | null;
  product_id?: string | null;
  uom_id?: string | null;
  sku_snapshot?: string | null;
  description: string;
  quantity: number;
  bin_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface DeliveryNoteListItem {
  id: string;
  client_id: string;
  dn_number: string;
  status: DeliveryNoteStatus;
  delivery_date: string;
  customer_purchase_order_id?: string | null;
  invoice_id?: string | null;
  warehouse_id: string;
  created_at?: string;
}

export interface DeliveryNote extends DeliveryNoteListItem {
  workspace_id?: string;
  bin_id?: string | null;
  shipping_address?: string | null;
  vehicle_number?: string | null;
  driver_name?: string | null;
  notes?: string | null;
  cancellation_reason?: string | null;
  confirmed_by?: string | null;
  confirmed_at?: string | null;
  items: DeliveryNoteItem[];
  updated_at?: string;
  deleted_at?: string | null;
}

export interface DeliveryNoteCreatePayload {
  customer_purchase_order_id?: string;
  invoice_id?: string;
  warehouse_id: string;
  bin_id?: string;
  delivery_date?: string;
  shipping_address?: string;
  vehicle_number?: string;
  driver_name?: string;
  notes?: string;
  items?: DeliveryNoteItemWrite[];
}

export interface DeliveryNoteUpdatePayload {
  warehouse_id?: string;
  bin_id?: string | null;
  delivery_date?: string;
  shipping_address?: string | null;
  vehicle_number?: string | null;
  driver_name?: string | null;
  notes?: string;
  items?: DeliveryNoteItemWrite[];
}

export interface DeliveryNoteListQuery {
  page?: number;
  per_page?: number;
  status?: DeliveryNoteStatus;
  client_id?: string;
  customer_purchase_order_id?: string;
  invoice_id?: string;
  search?: string;
}

export interface DeliveryNoteListResult {
  items: DeliveryNoteListItem[];
  pagination: PaginationMeta;
}

const BASE = '/api/v1/delivery-notes';

function listParams(query: DeliveryNoteListQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {
    page: query.page ?? 1,
    per_page: query.per_page ?? 20,
  };
  if (query.status) params.status = query.status;
  if (query.client_id) params.client_id = query.client_id;
  if (query.customer_purchase_order_id) {
    params.customer_purchase_order_id = query.customer_purchase_order_id;
  }
  if (query.invoice_id) params.invoice_id = query.invoice_id;
  if (query.search?.trim()) params.search = query.search.trim();
  return params;
}

function unwrapList(payload: PaginatedResponse<DeliveryNoteListItem>): DeliveryNoteListResult {
  const items = Array.isArray(payload.data) ? payload.data : [];
  return { items, pagination: payload.pagination };
}

function itemBody(item: DeliveryNoteItemWrite): Record<string, unknown> {
  const body: Record<string, unknown> = { quantity: item.quantity };
  if (item.customer_purchase_order_item_id) {
    body.customer_purchase_order_item_id = item.customer_purchase_order_item_id;
  }
  if (item.invoice_item_id) body.invoice_item_id = item.invoice_item_id;
  if (item.bin_id) body.bin_id = item.bin_id;
  return body;
}

function optionalText(value?: string | null): string | undefined {
  const trimmed = value?.trim();
  return trimmed || undefined;
}

export function createDeliveryNoteBody(
  data: DeliveryNoteCreatePayload,
): Record<string, unknown> {
  const body: Record<string, unknown> = { warehouse_id: data.warehouse_id };
  if (data.customer_purchase_order_id) {
    body.customer_purchase_order_id = data.customer_purchase_order_id;
  }
  if (data.invoice_id) body.invoice_id = data.invoice_id;
  if (data.bin_id) body.bin_id = data.bin_id;
  if (data.delivery_date) body.delivery_date = data.delivery_date;
  const address = optionalText(data.shipping_address);
  if (address) body.shipping_address = address;
  const vehicle = optionalText(data.vehicle_number);
  if (vehicle) body.vehicle_number = vehicle;
  const driver = optionalText(data.driver_name);
  if (driver) body.driver_name = driver;
  const notes = optionalText(data.notes);
  if (notes) body.notes = notes;
  if (data.items && data.items.length > 0) {
    body.items = data.items.map(itemBody);
  }
  return body;
}

export function updateDeliveryNoteBody(
  data: DeliveryNoteUpdatePayload,
): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (data.warehouse_id) body.warehouse_id = data.warehouse_id;
  if (data.bin_id) body.bin_id = data.bin_id;
  if (data.delivery_date) body.delivery_date = data.delivery_date;
  if (data.shipping_address !== undefined) {
    body.shipping_address = optionalText(data.shipping_address) ?? null;
  }
  if (data.vehicle_number !== undefined) {
    body.vehicle_number = optionalText(data.vehicle_number) ?? null;
  }
  if (data.driver_name !== undefined) {
    body.driver_name = optionalText(data.driver_name) ?? null;
  }
  if (data.notes !== undefined) body.notes = optionalText(data.notes);
  if (data.items && data.items.length > 0) {
    body.items = data.items.map(itemBody);
  }
  return body;
}

export const getDeliveryNotes = async (
  query: DeliveryNoteListQuery = {},
): Promise<DeliveryNoteListResult> => {
  const response = await apiClient.get<PaginatedResponse<DeliveryNoteListItem>>(BASE, {
    params: listParams(query),
  });
  return unwrapList(response.data);
};

export const getDeliveryNote = async (id: string): Promise<DeliveryNote> => {
  const response = await apiClient.get<SuccessResponse<DeliveryNote>>(`${BASE}/${id}`);
  return response.data.data;
};

export const createDeliveryNote = async (
  data: DeliveryNoteCreatePayload,
): Promise<DeliveryNote> => {
  const response = await apiClient.post<SuccessResponse<DeliveryNote>>(
    BASE,
    createDeliveryNoteBody(data),
  );
  return response.data.data;
};

export const updateDeliveryNote = async (
  id: string,
  data: DeliveryNoteUpdatePayload,
): Promise<DeliveryNote> => {
  const response = await apiClient.put<SuccessResponse<DeliveryNote>>(
    `${BASE}/${id}`,
    updateDeliveryNoteBody(data),
  );
  return response.data.data;
};

export const deleteDeliveryNote = async (id: string): Promise<void> => {
  await apiClient.delete(`${BASE}/${id}`);
};

export const confirmDeliveryNote = async (id: string): Promise<DeliveryNote> => {
  const response = await apiClient.post<SuccessResponse<DeliveryNote>>(
    `${BASE}/${id}/confirm`,
    {},
  );
  return response.data.data;
};

export const cancelDeliveryNote = async (
  id: string,
  reason?: string,
): Promise<DeliveryNote> => {
  const body: { reason?: string } = {};
  if (reason) body.reason = reason;
  const response = await apiClient.post<SuccessResponse<DeliveryNote>>(
    `${BASE}/${id}/cancel`,
    body,
  );
  return response.data.data;
};
