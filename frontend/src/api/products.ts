import { apiClient } from './client';
import type { PaginatedResponse, PaginationMeta, SuccessResponse } from '../types/api';

export const PRODUCT_PAGE_SIZE = 100;

export type IdentifierType =
  | 'MPN'
  | 'BARCODE'
  | 'SUPPLIER_CODE'
  | 'EAN'
  | 'UPC'
  | 'CUSTOMER_CODE';

export type PriceType = 'DEFAULT_SALES' | 'TIER_1' | 'CUSTOMER_SPECIFIC';

export interface ListQuery {
  page?: number;
  per_page?: number;
  search?: string;
}

export interface ProductListQuery extends ListQuery {
  category_id?: string;
  brand_id?: string;
  is_active?: boolean;
}

export interface ListResult<T> {
  items: T[];
  pagination: PaginationMeta;
}

export interface Category {
  id: string;
  workspace_id?: string;
  name: string;
  description: string | null;
  parent_id: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface Brand {
  id: string;
  workspace_id?: string;
  name: string;
  description: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface UnitOfMeasure {
  id: string;
  workspace_id?: string;
  code: string;
  name: string;
  created_at?: string;
  updated_at?: string;
}

export interface Product {
  id: string;
  workspace_id?: string;
  internal_sku: string;
  name: string;
  description: string | null;
  category_id: string | null;
  brand_id: string | null;
  base_uom_id: string;
  is_active: boolean;
  tax_rate: string | number | null;
  reorder_level: string | number | null;
  created_at?: string;
  updated_at?: string;
}

export interface ProductIdentifier {
  id: string;
  workspace_id?: string;
  product_id: string;
  type: IdentifierType | string;
  value: string;
}

export interface ProductConversion {
  id: string;
  workspace_id?: string;
  product_id: string;
  to_uom_id: string;
  conversion_factor: string | number;
  base_uom_id?: string | null;
}

export interface ProductPrice {
  id: string;
  workspace_id?: string;
  product_id: string;
  price_type: PriceType | string;
  currency: string;
  price: string | number;
  client_id: string | null;
  min_quantity: string | number | null;
}

export interface ProductDetail extends Product {
  identifiers: ProductIdentifier[];
  conversions: ProductConversion[];
  prices: ProductPrice[];
}

export interface CategoryWrite {
  name: string;
  description?: string | null;
  parent_id?: string | null;
}

export interface BrandWrite {
  name: string;
  description?: string | null;
}

export interface UomWrite {
  code: string;
  name: string;
}

export interface ProductWrite {
  internal_sku: string;
  name: string;
  base_uom_id: string;
  description?: string | null;
  category_id?: string | null;
  brand_id?: string | null;
  is_active?: boolean;
  tax_rate?: string | number | null;
  reorder_level?: string | number | null;
}

export interface IdentifierWrite {
  type: IdentifierType;
  value: string;
}

export interface ConversionWrite {
  to_uom_id: string;
  conversion_factor: string | number;
}

export interface PriceWrite {
  price_type: PriceType;
  currency?: 'AED';
  price: string | number;
  client_id?: string | null;
  min_quantity?: string | number | null;
}

function fallbackPagination(count: number): PaginationMeta {
  return {
    total: count,
    page: 1,
    per_page: count || PRODUCT_PAGE_SIZE,
    pages: count ? 1 : 0,
    has_next: false,
    has_prev: false,
  };
}

function unwrapList<T>(payload: PaginatedResponse<T>): ListResult<T> {
  const items = Array.isArray(payload.data) ? payload.data : [];
  return {
    items,
    pagination: payload.pagination ?? fallbackPagination(items.length),
  };
}

function listParams(query: ProductListQuery): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = {
    page: query.page ?? 1,
    per_page: query.per_page ?? PRODUCT_PAGE_SIZE,
  };
  if (query.search) params.search = query.search;
  if (query.category_id) params.category_id = query.category_id;
  if (query.brand_id) params.brand_id = query.brand_id;
  if (query.is_active !== undefined) params.is_active = query.is_active;
  return params;
}

async function getList<T>(path: string, query: ListQuery = {}): Promise<ListResult<T>> {
  const response = await apiClient.get<PaginatedResponse<T>>(path, {
    params: listParams(query),
  });
  return unwrapList(response.data);
}

async function getOne<T>(path: string): Promise<T> {
  const response = await apiClient.get<SuccessResponse<T>>(path);
  return response.data.data;
}

async function postOne<T>(path: string, body: unknown): Promise<T> {
  const response = await apiClient.post<SuccessResponse<T>>(path, body);
  return response.data.data;
}

async function putOne<T>(path: string, body: unknown): Promise<T> {
  const response = await apiClient.put<SuccessResponse<T>>(path, body);
  return response.data.data;
}

export const getCategories = (query: ListQuery = {}): Promise<ListResult<Category>> =>
  getList<Category>('/api/v1/products/categories', query);

export const getCategory = (id: string): Promise<Category> =>
  getOne<Category>(`/api/v1/products/categories/${id}`);

export const createCategory = (data: CategoryWrite): Promise<Category> =>
  postOne<Category>('/api/v1/products/categories', data);

export const updateCategory = (id: string, data: CategoryWrite): Promise<Category> =>
  putOne<Category>(`/api/v1/products/categories/${id}`, data);

export const deleteCategory = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/v1/products/categories/${id}`);
};

export const getBrands = (query: ListQuery = {}): Promise<ListResult<Brand>> =>
  getList<Brand>('/api/v1/products/brands', query);

export const getBrand = (id: string): Promise<Brand> =>
  getOne<Brand>(`/api/v1/products/brands/${id}`);

export const createBrand = (data: BrandWrite): Promise<Brand> =>
  postOne<Brand>('/api/v1/products/brands', data);

export const updateBrand = (id: string, data: BrandWrite): Promise<Brand> =>
  putOne<Brand>(`/api/v1/products/brands/${id}`, data);

export const deleteBrand = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/v1/products/brands/${id}`);
};

export const getUOMs = (query: ListQuery = {}): Promise<ListResult<UnitOfMeasure>> =>
  getList<UnitOfMeasure>('/api/v1/products/uom', query);

export const getUOM = (id: string): Promise<UnitOfMeasure> =>
  getOne<UnitOfMeasure>(`/api/v1/products/uom/${id}`);

export const createUOM = (data: UomWrite): Promise<UnitOfMeasure> =>
  postOne<UnitOfMeasure>('/api/v1/products/uom', data);

export const updateUOM = (id: string, data: UomWrite): Promise<UnitOfMeasure> =>
  putOne<UnitOfMeasure>(`/api/v1/products/uom/${id}`, data);

export const deleteUOM = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/v1/products/uom/${id}`);
};

export const getProducts = (query: ProductListQuery = {}): Promise<ListResult<Product>> =>
  getList<Product>('/api/v1/products', query);

export const getProduct = (id: string): Promise<ProductDetail> =>
  getOne<ProductDetail>(`/api/v1/products/${id}`);

export const createProduct = (data: ProductWrite): Promise<Product> =>
  postOne<Product>('/api/v1/products', data);

export const updateProduct = (id: string, data: ProductWrite): Promise<Product> =>
  putOne<Product>(`/api/v1/products/${id}`, data);

export const deleteProduct = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/v1/products/${id}`);
};

export const getProductIdentifiers = (productId: string): Promise<ProductIdentifier[]> =>
  getOne<ProductIdentifier[]>(`/api/v1/products/${productId}/identifiers`);

export const createProductIdentifier = (
  productId: string,
  data: IdentifierWrite,
): Promise<ProductIdentifier> =>
  postOne<ProductIdentifier>(`/api/v1/products/${productId}/identifiers`, data);

export const deleteProductIdentifier = async (
  productId: string,
  identifierId: string,
): Promise<void> => {
  await apiClient.delete(`/api/v1/products/${productId}/identifiers/${identifierId}`);
};

export const getProductConversions = (productId: string): Promise<ProductConversion[]> =>
  getOne<ProductConversion[]>(`/api/v1/products/${productId}/conversions`);

export const createProductConversion = (
  productId: string,
  data: ConversionWrite,
): Promise<ProductConversion> =>
  postOne<ProductConversion>(`/api/v1/products/${productId}/conversions`, data);

export const deleteProductConversion = async (
  productId: string,
  conversionId: string,
): Promise<void> => {
  await apiClient.delete(`/api/v1/products/${productId}/conversions/${conversionId}`);
};

export const getProductPrices = (productId: string): Promise<ProductPrice[]> =>
  getOne<ProductPrice[]>(`/api/v1/products/${productId}/prices`);

export const createProductPrice = (productId: string, data: PriceWrite): Promise<ProductPrice> =>
  postOne<ProductPrice>(`/api/v1/products/${productId}/prices`, data);

export const deleteProductPrice = async (productId: string, priceId: string): Promise<void> => {
  await apiClient.delete(`/api/v1/products/${productId}/prices/${priceId}`);
};
