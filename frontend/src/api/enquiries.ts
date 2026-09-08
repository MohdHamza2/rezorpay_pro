import { apiClient } from './client';
import type { Quotation } from './quotations';

export type EnquiryStatus = 'NEW' | 'IN_PROGRESS' | 'QUOTED' | 'CLOSED';
export type EnquirySource = 'WHATSAPP' | 'EMAIL' | 'PHONE' | 'WALK_IN' | 'MANUAL';

export interface EnquiryItemWrite {
  product_id?: string | null;
  description: string;
  quantity_requested: number;
  uom_id?: string | null;
  notes?: string | null;
}

export interface EnquiryItem extends EnquiryItemWrite {
  id: string;
  enquiry_id: string;
}

export interface EnquiryCreate {
  client_id?: string | null;
  source: EnquirySource;
  contact_name?: string | null;
  contact_phone?: string | null;
  contact_whatsapp?: string | null;
  contact_email?: string | null;
  items_description?: string | null;
  whatsapp_message_id?: string | null;
  notes?: string | null;
  assigned_to?: string | null;
  items?: EnquiryItemWrite[];
}

export interface EnquiryUpdate {
  client_id?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  contact_whatsapp?: string | null;
  contact_email?: string | null;
  items_description?: string | null;
  notes?: string | null;
  assigned_to?: string | null;
}

export interface EnquiryRead {
  id: string;
  workspace_id: string;
  enquiry_number: string;
  client_id?: string | null;
  source: EnquirySource;
  status: EnquiryStatus;
  contact_name?: string | null;
  contact_phone?: string | null;
  contact_whatsapp?: string | null;
  contact_email?: string | null;
  items_description?: string | null;
  whatsapp_message_id?: string | null;
  notes?: string | null;
  assigned_to?: string | null;
  created_at: string;
  updated_at: string;
  items: EnquiryItem[];
}

export interface EnquiryListResponse {
  items: EnquiryRead[];
  total: number;
  page: number;
  size: number;
}

export interface EnquiryListQuery {
  skip?: number;
  limit?: number;
  status?: EnquiryStatus;
  client_id?: string;
  search?: string;
}

function listParams(query: EnquiryListQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {
    skip: query.skip ?? 0,
    limit: query.limit ?? 20,
  };
  if (query.status) params.status = query.status;
  if (query.client_id) params.client_id = query.client_id;
  if (query.search?.trim()) params.search = query.search.trim();
  return params;
}

export const getEnquiries = async (
  query: EnquiryListQuery = {},
): Promise<EnquiryListResponse> => {
  const response = await apiClient.get<EnquiryListResponse>('/api/v1/enquiries', {
    params: listParams(query),
  });
  return response.data;
};

export const getEnquiry = async (id: string): Promise<EnquiryRead> => {
  const response = await apiClient.get<EnquiryRead>(`/api/v1/enquiries/${id}`);
  return response.data;
};

export const createEnquiry = async (data: EnquiryCreate): Promise<EnquiryRead> => {
  const response = await apiClient.post<EnquiryRead>('/api/v1/enquiries', data);
  return response.data;
};

export const updateEnquiry = async (
  id: string,
  data: EnquiryUpdate,
): Promise<EnquiryRead> => {
  const response = await apiClient.put<EnquiryRead>(`/api/v1/enquiries/${id}`, data);
  return response.data;
};

export const updateEnquiryStatus = async (
  id: string,
  status: EnquiryStatus,
): Promise<EnquiryRead> => {
  const response = await apiClient.post<EnquiryRead>(
    `/api/v1/enquiries/${id}/status`,
    { status },
  );
  return response.data;
};

export const convertEnquiryToQuotation = async (id: string): Promise<Quotation> => {
  const response = await apiClient.post<Quotation>(
    `/api/v1/enquiries/${id}/convert`,
  );
  return response.data;
};
