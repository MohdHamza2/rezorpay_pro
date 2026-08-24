import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export interface Warehouse {
  id: string;
  code: string;
  name: string;
  location: string | null;
  is_active: boolean;
  created_at: string;
}

export interface InventoryLevel {
  id: string;
  product_id: string;
  warehouse_id: string;
  bin_id: string;
  on_hand: number;
  reserved: number;
  damaged: number;
  available: number;
}

export const getWarehouses = async (): Promise<Warehouse[]> => {
  const response = await apiClient.get<SuccessResponse<Warehouse[]>>('/api/v1/inventory/warehouses');
  return response.data.data;
};

export const createWarehouse = async (data: Partial<Warehouse>): Promise<Warehouse> => {
  const response = await apiClient.post<SuccessResponse<Warehouse>>('/api/v1/inventory/warehouses', data);
  return response.data.data;
};

export const getInventoryLevels = async (productId?: string): Promise<InventoryLevel[]> => {
  const url = productId ? '/api/v1/inventory/levels?product_id=' + productId : '/api/v1/inventory/levels';
  const response = await apiClient.get<SuccessResponse<InventoryLevel[]>>(url);
  return response.data.data;
};
