import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  trn: string | null;
  address: string | null;
  logo_url: string | null;
  whatsapp_number: string | null;
  default_tax_rate: number;
  credit_limit_default: number;
  credit_warning_days: number;
  credit_hold_days: number;
  block_po_on_hold: boolean;
  created_at: string;
  updated_at: string;
}

export const getCurrentWorkspace = async (): Promise<Workspace> => {
  const response = await apiClient.get<SuccessResponse<Workspace>>('/api/v1/workspaces/me');
  return response.data.data;
};

export const updateCurrentWorkspace = async (data: Partial<Workspace>): Promise<Workspace> => {
  const response = await apiClient.put<SuccessResponse<Workspace>>('/api/v1/workspaces/me', data);
  return response.data.data;
};
