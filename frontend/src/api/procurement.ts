import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export interface ProcurementRequestItem {
  id: string;
  product_id: string;
  uom_id: string;
  requested_quantity: number;
  approved_quantity: number;
  ordered_quantity: number;
  received_quantity: number;
}

export interface ProcurementRequest {
  id: string;
  request_number: string;
  source_type: string;
  destination_type: string;
  priority: string;
  procurement_method: string;
  required_by_date: string;
  status: string;
  items: ProcurementRequestItem[];
}

export const getProcurementRequests = async (): Promise<ProcurementRequest[]> => {
  const response = await apiClient.get<SuccessResponse<ProcurementRequest[]>>('/api/v1/procurement/requests');
  return response.data.data;
};
