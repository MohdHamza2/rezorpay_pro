import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export interface Supplier {
  id: string;
  supplier_code: string;
  name: string;
  trade_name: string | null;
  trn: string | null;
  credit_limit: number | null;
  payment_terms: string;
  status: string;
  rating: string | null;
  address: string | null;
  city: string | null;
  country: string | null;
  created_at: string;
  updated_at: string;
}

export const getSuppliers = async (): Promise<Supplier[]> => {
  const response = await apiClient.get<SuccessResponse<Supplier[]>>('/api/v1/suppliers');
  return response.data.data;
};

export const createSupplier = async (data: Partial<Supplier>): Promise<Supplier> => {
  const response = await apiClient.post<SuccessResponse<Supplier>>('/api/v1/suppliers', data);
  return response.data.data;
};
