import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export interface Client {
  id: string;
  name: string;
  email: string;
  address?: string | null;
  phone?: string;
  tax_id?: string | null;
  created_at: string;
}

export const getClients = async (): Promise<Client[]> => {
  const response = await apiClient.get<SuccessResponse<Client[]>>('/api/v1/clients');
  return response.data.data;
};

export const createClient = async (data: Partial<Client>): Promise<Client> => {
  const response = await apiClient.post<SuccessResponse<Client>>('/api/v1/clients', data);
  return response.data.data;
};

export const updateClient = async (id: string, data: Partial<Client>): Promise<Client> => {
  const response = await apiClient.put<SuccessResponse<Client>>(`/api/v1/clients/${id}`, data);
  return response.data.data;
};

export const deleteClient = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/v1/clients/${id}`);
};
