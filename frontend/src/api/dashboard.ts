import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export interface DashboardStats {
  total_invoices: number;
  outstanding_balance: number;
  pending_prs: number;
  active_rfqs: number;
  unposted_grns: number;
}

export const getDashboardStats = async (): Promise<DashboardStats> => {
  const response = await apiClient.get<SuccessResponse<DashboardStats>>('/api/v1/dashboard/stats');
  return response.data.data;
};
