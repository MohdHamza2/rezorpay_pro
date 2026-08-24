import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export type InvoiceStatus = 'DRAFT' | 'SENT' | 'PARTIALLY_PAID' | 'PAID' | 'CANCELLED';

export interface InvoiceItem {
  id?: string;
  description: string;
  quantity: number;
  unit_price: number;
  total_price: number;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  client_id: string;
  status: InvoiceStatus;
  issue_date: string;
  due_date: string;
  subtotal: number;
  tax_amount: number;
  total_amount: number;
  amount_paid: number;
  balance_due: number;
  items: InvoiceItem[];
}

export const getInvoices = async (): Promise<Invoice[]> => {
  const response = await apiClient.get<SuccessResponse<Invoice[]>>('/api/v1/invoices');
  return response.data.data;
};

export const getInvoice = async (id: string): Promise<Invoice> => {
  const response = await apiClient.get<SuccessResponse<Invoice>>('/api/v1/invoices/' + id);
  return response.data.data;
};

export const createInvoice = async (data: Partial<Invoice>): Promise<Invoice> => {
  const response = await apiClient.post<SuccessResponse<Invoice>>('/api/v1/invoices', data);
  return response.data.data;
};

export const updateInvoice = async (id: string, data: Partial<Invoice>): Promise<Invoice> => {
  const response = await apiClient.put<SuccessResponse<Invoice>>('/api/v1/invoices/' + id, data);
  return response.data.data;
};

export const sendInvoice = async (id: string, data: any): Promise<Invoice> => {
  const response = await apiClient.post<SuccessResponse<Invoice>>('/api/v1/invoices/' + id + '/send', data);
  return response.data.data;
};

export const voidInvoice = async (id: string, reason: string): Promise<Invoice> => {
  const response = await apiClient.post<SuccessResponse<Invoice>>('/api/v1/invoices/' + id + '/void', { reason });
  return response.data.data;
};

export interface PaymentData {
  amount: number;
  payment_method: string;
  payment_date?: string;
  reference_number?: string;
  bank_name?: string;
  pdc_date?: string;
  pdc_status?: string;
}

export const recordPayment = async (id: string, data: PaymentData): Promise<any> => {
  const idempotencyKey = crypto.randomUUID();
  const response = await apiClient.post<SuccessResponse<any>>(
    '/api/v1/invoices/' + id + '/payments',
    data,
    { headers: { 'Idempotency-Key': idempotencyKey } }
  );
  return response.data.data;
};
