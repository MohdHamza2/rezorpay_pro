import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export interface RFQItem {
  id: string;
  product_id: string;
  uom_id: string;
  quantity: number;
  awarded_quantity: number;
}

export interface RFQ {
  id: string;
  rfq_number: string;
  rfq_type: string;
  status: string;
  deadline: string;
  currency: string;
  items: RFQItem[];
}

export const getRFQs = async (): Promise<RFQ[]> => {
  const response = await apiClient.get<SuccessResponse<RFQ[]>>('/api/v1/rfq/requests');
  return response.data.data;
};
