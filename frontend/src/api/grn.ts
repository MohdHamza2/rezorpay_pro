import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export interface GRNItem {
  id: string;
  grn_id: string;
  spo_item_id: string;
  product_id: string;
  internal_sku: string;
  description: string;
  uom_id: string;
  quantity_ordered_snapshot: number;
  quantity_confirmed_snapshot: number;
  quantity_received: number;
  quantity_accepted: number;
  quantity_damaged: number;
  quantity_rejected: number;
  damage_reason?: string;
  rejection_reason?: string;
  batch_number?: string;
  expiry_date?: string;
  status?: string;
}

export interface GRN {
  id: string;
  grn_number: string;
  supplier_id: string;
  spo_id: string | null;
  warehouse_id: string;
  status: 'DRAFT' | 'RECEIVING' | 'PENDING_INSPECTION' | 'PARTIALLY_ACCEPTED' | 'ACCEPTED' | 'PARTIALLY_REJECTED' | 'REJECTED' | 'CANCELLED';
  received_date: string;
  delivery_reference: string | null;
  stock_posted: boolean;
  items: GRNItem[];
}

export interface GRNItemCreate {
  spo_item_id: string;
  product_id: string;
  internal_sku: string;
  description: string;
  uom_id: string;
  quantity_received: number;
}

export interface GRNDispositionRequest {
  quantity_accepted: number;
  quantity_damaged: number;
  quantity_rejected: number;
  damage_reason?: string;
  rejection_reason?: string;
}

export const getGRNs = async (): Promise<GRN[]> => {
  const response = await apiClient.get<SuccessResponse<GRN[]>>('/api/v1/grns');
  return response.data.data;
};

export const getGRNReconciliation = async (id: string): Promise<GRN> => {
  const response = await apiClient.get<SuccessResponse<GRN>>(`/api/v1/grns/${id}/reconciliation`);
  return response.data.data;
};

export const startReceiving = async (id: string): Promise<GRN> => {
  const response = await apiClient.post<SuccessResponse<GRN>>(`/api/v1/grns/${id}/start-receiving`);
  return response.data.data;
};

export const stageForInspection = async (id: string): Promise<GRN> => {
  const response = await apiClient.post<SuccessResponse<GRN>>(`/api/v1/grns/${id}/stage-for-inspection`);
  return response.data.data;
};

export const addGRNItem = async (id: string, data: GRNItemCreate): Promise<GRN> => {
  const response = await apiClient.post<SuccessResponse<GRN>>(`/api/v1/grns/${id}/items`, data);
  return response.data.data;
};

export const recordDisposition = async (id: string, itemId: string, data: GRNDispositionRequest): Promise<GRN> => {
  const response = await apiClient.post<SuccessResponse<GRN>>(`/api/v1/grns/${id}/items/${itemId}/disposition`, data);
  return response.data.data;
};
