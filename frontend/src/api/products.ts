import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export interface Category {
  id: string;
  name: string;
  description: string | null;
  parent_id: string | null;
}

export interface Brand {
  id: string;
  name: string;
  description: string | null;
}

export interface UnitOfMeasure {
  id: string;
  code: string;
  name: string;
}

export interface Product {
  id: string;
  internal_sku: string;
  name: string;
  description: string | null;
  category_id: string | null;
  brand_id: string | null;
  base_uom_id: string;
  is_active: boolean;
  tax_rate: number | null;
  reorder_level: number | null;
}

export const getCategories = async (): Promise<Category[]> => {
  const response = await apiClient.get<SuccessResponse<Category[]>>('/api/v1/products/categories');
  return response.data.data;
};

export const getBrands = async (): Promise<Brand[]> => {
  const response = await apiClient.get<SuccessResponse<Brand[]>>('/api/v1/products/brands');
  return response.data.data;
};

export const getUOMs = async (): Promise<UnitOfMeasure[]> => {
  const response = await apiClient.get<SuccessResponse<UnitOfMeasure[]>>('/api/v1/products/uom');
  return response.data.data;
};

export const getProducts = async (): Promise<Product[]> => {
  const response = await apiClient.get<SuccessResponse<Product[]>>('/api/v1/products');
  return response.data.data;
};

export const createProduct = async (data: Partial<Product>): Promise<Product> => {
  const response = await apiClient.post<SuccessResponse<Product>>('/api/v1/products', data);
  return response.data.data;
};
