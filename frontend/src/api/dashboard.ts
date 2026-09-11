import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export interface DashboardStats {
  total_invoices: number;
  outstanding_balance: number;
  pending_prs: number;
  active_rfqs: number;
  unposted_grns: number;
  // AR PDC Outstanding — operational PDC instrument metric, not a balance due component
  ar_pdc_outstanding_count: number;
  ar_pdc_outstanding_amount: number;
}

export const getDashboardStats = async (): Promise<DashboardStats> => {
  const response = await apiClient.get<SuccessResponse<DashboardStats>>('/api/v1/dashboard/stats');
  return response.data.data;
};
