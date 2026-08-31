import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export type CreditStatus = 'ACTIVE' | 'WARNING' | 'HOLD';

export interface CreditBuckets {
  current: number | string;
  days_1_30: number | string;
  days_31_60: number | string;
  days_61_90: number | string;
  days_90_plus: number | string;
}

export interface ClientCredit {
  credit_status: CreditStatus;
  credit_limit: number | string | null;
  effective_credit_limit: number | string;
  payment_terms_days: number;
  exposure: number | string;
  oldest_overdue_days: number | null;
  buckets: CreditBuckets;
}

/** GET/list row. Do not POST/PUT this shape — extra keys 422. */
export interface Client {
  id: string;
  name: string;
  email: string;
  address?: string | null;
  phone?: string;
  tax_id?: string | null;
  credit_limit?: number | string | null;
  payment_terms_days?: number;
  credit_status?: CreditStatus;
  effective_credit_limit?: number | string;
  exposure?: number | string;
  created_at: string;
}

/** WP-A ClientCreate/ClientUpdate only (`extra="forbid"`). */
export interface ClientWritePayload {
  name: string;
  email?: string;
  phone?: string;
  address?: string;
  tax_id?: string;
  credit_limit?: number | null;
  payment_terms_days?: number;
}

export const getClients = async (): Promise<Client[]> => {
  const response = await apiClient.get<SuccessResponse<Client[]>>('/api/v1/clients');
  return response.data.data;
};

export const getClientCredit = async (id: string): Promise<ClientCredit> => {
  const response = await apiClient.get<SuccessResponse<ClientCredit>>(
    `/api/v1/clients/${id}/credit`,
  );
  return response.data.data;
};

export const createClient = async (data: ClientWritePayload): Promise<Client> => {
  const response = await apiClient.post<SuccessResponse<Client>>('/api/v1/clients', data);
  return response.data.data;
};

export const updateClient = async (id: string, data: ClientWritePayload): Promise<Client> => {
  const response = await apiClient.put<SuccessResponse<Client>>(`/api/v1/clients/${id}`, data);
  return response.data.data;
};

export const deleteClient = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/v1/clients/${id}`);
};
