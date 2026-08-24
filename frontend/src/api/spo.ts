import { apiClient } from './client';

export interface SPOItem {
  id: string;
  spo_id: string;
  line_number: number;
  product_id: string;
  internal_sku: string | null;
  supplier_sku: string | null;
  description: string;
  uom_id: string;
  quantity_ordered: number;
  quantity_confirmed: number;
  quantity_backordered: number;
  quantity_received: number;
  quantity_accepted: number;
  quantity_damaged_rejected: number;
  quantity_invoiced: number;
  quantity_cancelled: number;
  open_quantity: number;
  unit_price: number;
  discount_percent: number;
  vat_rate: number;
  vat_amount: number;
  total_price: number;
  expected_delivery_date: string | null;
  price_amendment_pending: boolean;
}

export interface SPO {
  id: string;
  workspace_id: string;
  supplier_id: string;
  spo_number: string;
  rfq_id: string | null;
  procurement_request_id: string | null;
  procurement_method: string;
  single_source_justification: string | null;
  supplier_reference: string | null;
  status: string;
  po_date: string | null;
  expected_delivery_date: string | null;
  warehouse_id: string;
  currency: string;
  payment_terms_days: number;
  delivery_terms: string | null;
  subtotal: number;
  vat_amount: number;
  total_amount: number;
  quantity_ordered_total: number;
  quantity_confirmed_total: number;
  quantity_backordered_total: number;
  has_open_amendment: boolean;
  approved_by: string | null;
  approved_at: string | null;
  sent_at: string | null;
  acknowledged_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  items: SPOItem[];
}

export const getSPOs = async (workspaceId?: string): Promise<SPO[]> => {
  const params = workspaceId ? { workspace_id: workspaceId } : {};
  const response = await apiClient.get<SPO[]>('/api/v1/spos', { params });
  // Some endpoints might return SuccessResponse wrapped, but usually FastAPI returns the model directly unless wrapped.
  // Based on the schema provided, the backend returns SPOResponse (which is just the object) directly, not wrapped.
  // We'll return response.data directly assuming it's an array for list.
  return Array.isArray(response.data) ? response.data : (response.data as any).data;
};

export const getSPO = async (id: string): Promise<SPO> => {
  const response = await apiClient.get<SPO>(`/api/v1/spos/${id}`);
  return response.data;
};

export const createSPO = async (workspaceId: string, data: any): Promise<SPO> => {
  const response = await apiClient.post<SPO>(`/api/v1/spos/?workspace_id=${workspaceId}`, data);
  return response.data;
};

export const submitSPO = async (id: string): Promise<SPO> => {
  const response = await apiClient.post<SPO>(`/api/v1/spos/${id}/submit-approval`);
  return response.data;
};

export const approveSPO = async (id: string): Promise<SPO> => {
  const response = await apiClient.post<SPO>(`/api/v1/spos/${id}/approve`);
  return response.data;
};

export const sendSPO = async (id: string): Promise<SPO> => {
  const response = await apiClient.post<SPO>(`/api/v1/spos/${id}/send`);
  return response.data;
};

export const acknowledgeSPO = async (id: string, data: any): Promise<SPO> => {
  const response = await apiClient.post<SPO>(`/api/v1/spos/${id}/items/acknowledge`, data);
  return response.data;
};

export const cancelSPO = async (id: string, reason: string): Promise<SPO> => {
  const response = await apiClient.post<SPO>(`/api/v1/spos/${id}/cancel?reason=${encodeURIComponent(reason)}`);
  return response.data;
};
