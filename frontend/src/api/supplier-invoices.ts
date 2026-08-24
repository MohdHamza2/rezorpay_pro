import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export interface SupplierInvoiceItem {
  id: string;
  supplier_invoice_id: string;
  spo_item_id: string | null;
  grn_item_id: string | null;
  product_id: string;
  description: string;
  quantity: number;
  uom_id: string;
  unit_price: number;
  discount_percent: number;
  vat_rate: number;
  vat_amount: number;
  total_price: number;
  currency: string;
  match_status: string;
  variance_quantity: number;
  variance_price: number;
  variance_tax: number;
  variance_notes: string | null;
}

export interface SupplierInvoice {
  id: string;
  workspace_id: string;
  supplier_id: string;
  supplier_invoice_number: string;
  our_reference: string | null;
  invoice_date: string;
  due_date: string;
  currency: string;
  subtotal: number;
  discount_amount: number;
  vat_amount: number;
  total_amount: number;
  amount_paid: number;
  balance_due: number;
  status: 'RECEIVED' | 'PENDING_MATCHING' | 'MATCHED' | 'DISCREPANCY' | 'APPROVED' | 'PARTIALLY_PAID' | 'PAID' | 'CANCELLED';
  three_way_match_status: string;
  three_way_match_notes: string | null;
  document_url: string | null;
  ocr_job_id: string | null;
  ocr_extracted: boolean;
  primary_spo_id: string | null;
  received_at: string;
  matched_at: string | null;
  approved_at: string | null;
  paid_at: string | null;
  created_at: string;
  updated_at: string;
  items: SupplierInvoiceItem[];
}

export interface SupplierInvoiceItemCreate {
  spo_item_id?: string | null;
  grn_item_id?: string | null;
  product_id: string;
  description: string;
  quantity: number;
  uom_id: string;
  unit_price: number;
  discount_percent?: number;
  vat_rate?: number;
  vat_amount?: number;
  total_price?: number;
  currency: string;
}

export interface SupplierInvoiceCreate {
  supplier_id: string;
  supplier_invoice_number: string;
  our_reference?: string | null;
  invoice_date: string;
  due_date: string;
  currency: string;
  subtotal: number;
  discount_amount: number;
  vat_amount: number;
  total_amount: number;
  primary_spo_id?: string | null;
  items: SupplierInvoiceItemCreate[];
}

export const getSupplierInvoices = async (): Promise<SupplierInvoice[]> => {
  const response = await apiClient.get<SuccessResponse<SupplierInvoice[]>>('/api/v1/supplier-invoices');
  return response.data.data;
};

export const getSupplierInvoice = async (id: string): Promise<SupplierInvoice> => {
  const response = await apiClient.get<SuccessResponse<SupplierInvoice>>(`/api/v1/supplier-invoices/${id}`);
  return response.data.data;
};

export const createSupplierInvoice = async (data: SupplierInvoiceCreate): Promise<SupplierInvoice> => {
  const response = await apiClient.post<SuccessResponse<SupplierInvoice>>('/api/v1/supplier-invoices', data);
  return response.data.data;
};

export const submitMatching = async (id: string): Promise<SupplierInvoice> => {
  const response = await apiClient.post<SuccessResponse<SupplierInvoice>>(`/api/v1/supplier-invoices/${id}/submit-matching`);
  return response.data.data;
};

export const resolveDiscrepancy = async (id: string, notes: string): Promise<SupplierInvoice> => {
  const response = await apiClient.post<SuccessResponse<SupplierInvoice>>(`/api/v1/supplier-invoices/${id}/resolve-discrepancy`, { notes });
  return response.data.data;
};

export const approveInvoice = async (id: string): Promise<SupplierInvoice> => {
  const response = await apiClient.post<SuccessResponse<SupplierInvoice>>(`/api/v1/supplier-invoices/${id}/approve`);
  return response.data.data;
};
