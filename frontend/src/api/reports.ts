import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export interface CreditBuckets {
  current: number;
  days_1_30: number;
  days_31_60: number;
  days_61_90: number;
  days_90_plus: number;
}

export interface ArAgingSummary {
  as_of: string;
  client_count: number;
  invoice_count: number;
  total_outstanding: number;
  buckets: CreditBuckets;
  // AR PDC Outstanding — operational PDC instrument metric, not a balance due component
  pdc_outstanding_count: number;
  pdc_outstanding_amount: number;
}

export interface ArAgingDetailRow {
  client_id: string;
  client_name: string;
  invoice_id: string;
  invoice_number: string;
  issue_date: string;
  due_date: string;
  days_overdue: number;
  balance_due: number;
  bucket: string;
  // Per-invoice PDC outstanding aggregate (RECEIVED + DEPOSITED only)
  pdc_outstanding_count: number;
  pdc_outstanding_amount: number;
}

export interface ArAgingDetail {
  as_of: string;
  total_outstanding: number;
  buckets: CreditBuckets;
  invoices: ArAgingDetailRow[];
  // PDC Outstanding aggregates
  pdc_outstanding_count: number;
  pdc_outstanding_amount: number;
}

export interface ArAgingCustomerRow {
  client: { id: string; name: string };
  total_outstanding: number;
  buckets: CreditBuckets;
  // Per-client PDC outstanding aggregate (RECEIVED + DEPOSITED only)
  pdc_outstanding_count: number;
  pdc_outstanding_amount: number;
}

export interface ArAgingByCustomer {
  as_of: string;
  total_outstanding: number;
  buckets: CreditBuckets;
  customers: ArAgingCustomerRow[];
  // PDC Outstanding aggregates
  pdc_outstanding_count: number;
  pdc_outstanding_amount: number;
}

export interface ApAgingSummary {
  as_of: string;
  supplier_count: number;
  invoice_count: number;
  total_outstanding: number;
  buckets: CreditBuckets;
  // AP PDC Outstanding — operational PDC instrument metric, not a balance due component
  pdc_outstanding_count: number;
  pdc_outstanding_amount: number;
  // AP Landed Cost Outstanding (D-22) — operational landed cost metric, not a balance due component
  landed_cost_outstanding_count: number;
  landed_cost_outstanding_amount: number;
}

export interface ApAgingDetailRow {
  supplier_id: string;
  supplier_name: string;
  supplier_invoice_id: string;
  supplier_invoice_number: string;
  invoice_date: string;
  due_date: string;
  days_overdue: number;
  balance_due: number;
  bucket: string;
  // Per-supplier-invoice PDC outstanding aggregate (RECEIVED + DEPOSITED only)
  pdc_outstanding_count: number;
  pdc_outstanding_amount: number;
  // Per-supplier-invoice Landed Cost outstanding aggregate (D-22, CAPITALIZED only)
  landed_cost_outstanding_count: number;
  landed_cost_outstanding_amount: number;
}

export interface ApAgingDetail {
  as_of: string;
  total_outstanding: number;
  buckets: CreditBuckets;
  invoices: ApAgingDetailRow[];
  // PDC Outstanding aggregates
  pdc_outstanding_count: number;
  pdc_outstanding_amount: number;
  // Landed Cost Outstanding aggregates (D-22)
  landed_cost_outstanding_count: number;
  landed_cost_outstanding_amount: number;
}

export interface ApAgingSupplierRow {
  supplier: { id: string; name: string; supplier_code: string };
  total_outstanding: number;
  buckets: CreditBuckets;
  // Per-supplier PDC outstanding aggregate (RECEIVED + DEPOSITED only)
  pdc_outstanding_count: number;
  pdc_outstanding_amount: number;
  // Per-supplier Landed Cost outstanding aggregate (D-22, CAPITALIZED only)
  landed_cost_outstanding_count: number;
  landed_cost_outstanding_amount: number;
}

export interface ApAgingBySupplier {
  as_of: string;
  total_outstanding: number;
  buckets: CreditBuckets;
  suppliers: ApAgingSupplierRow[];
  // PDC Outstanding aggregates
  pdc_outstanding_count: number;
  pdc_outstanding_amount: number;
  // Landed Cost Outstanding aggregates (D-22)
  landed_cost_outstanding_count: number;
  landed_cost_outstanding_amount: number;
}

export const getArAgingSummary = async (
  asOf?: string,
  clientId?: string,
  historical = false
): Promise<ArAgingSummary> => {
  const params: Record<string, string> = {};
  if (asOf) params.as_of = asOf;
  if (clientId) params.client_id = clientId;
  if (historical) params.historical = 'true';
  const response = await apiClient.get<SuccessResponse<ArAgingSummary>>(
    '/api/v1/ar-aging',
    { params }
  );
  return response.data.data;
};

export const getArAgingDetail = async (
  asOf?: string,
  clientId?: string,
  historical = false
): Promise<ArAgingDetail> => {
  const params: Record<string, string> = {};
  if (asOf) params.as_of = asOf;
  if (clientId) params.client_id = clientId;
  if (historical) params.historical = 'true';
  const response = await apiClient.get<SuccessResponse<ArAgingDetail>>(
    '/api/v1/ar-aging/detail',
    { params }
  );
  return response.data.data;
};

export const getArAgingByCustomer = async (
  asOf?: string,
  historical = false
): Promise<ArAgingByCustomer> => {
  const params: Record<string, string> = {};
  if (asOf) params.as_of = asOf;
  if (historical) params.historical = 'true';
  const response = await apiClient.get<SuccessResponse<ArAgingByCustomer>>(
    '/api/v1/ar-aging/by-customer',
    { params }
  );
  return response.data.data;
};

export const getApAgingSummary = async (
  asOf?: string,
  supplierId?: string
): Promise<ApAgingSummary> => {
  const params: Record<string, string> = {};
  if (asOf) params.as_of = asOf;
  if (supplierId) params.supplier_id = supplierId;
  const response = await apiClient.get<SuccessResponse<ApAgingSummary>>(
    '/api/v1/ap-aging',
    { params }
  );
  return response.data.data;
};

export const getApAgingDetail = async (
  asOf?: string,
  supplierId?: string
): Promise<ApAgingDetail> => {
  const params: Record<string, string> = {};
  if (asOf) params.as_of = asOf;
  if (supplierId) params.supplier_id = supplierId;
  const response = await apiClient.get<SuccessResponse<ApAgingDetail>>(
    '/api/v1/ap-aging/detail',
    { params }
  );
  return response.data.data;
};

export const getApAgingBySupplier = async (
  asOf?: string
): Promise<ApAgingBySupplier> => {
  const params: Record<string, string> = {};
  if (asOf) params.as_of = asOf;
  const response = await apiClient.get<SuccessResponse<ApAgingBySupplier>>(
    '/api/v1/ap-aging/by-supplier',
    { params }
  );
  return response.data.data;
};

export interface VatComplianceJson {
  manifest: {
    generator: string;
    version: string;
    generated_at: string;
    period: { from: string; to: string };
    org: { name: string; trn?: string };
    currency: string;
    warnings: string[];
    summary: {
      total_sales_vat: number;
      total_input_vat: number;
      [key: string]: unknown;
    };
    files: string[];
    excluded: Record<string, unknown>;
  };
  sales_invoices: unknown[];
  invoice_lines: unknown[];
  credit_notes: unknown[];
  tax_debit_notes: unknown[];
  purchase_invoices: unknown[];
  vat_summary: Record<string, unknown>[];
}

export const downloadVatComplianceZip = async (
  from: string,
  to: string
): Promise<Blob> => {
  const response = await apiClient.get('/api/v1/reports/vat-compliance', {
    params: { from, to, format: 'csv' },
    responseType: 'blob',
  });
  return response.data as Blob;
};

export const getVatComplianceJson = async (
  from: string,
  to: string
): Promise<VatComplianceJson> => {
  const response = await apiClient.get<SuccessResponse<VatComplianceJson>>(
    '/api/v1/reports/vat-compliance',
    { params: { from, to, format: 'json' } }
  );
  return response.data.data;
};

export const exportStatementBlob = async (
  kind: 'ar' | 'ap',
  id: string,
  from: string,
  to: string,
  as_of: string,
  format: 'pdf' | 'csv'
): Promise<Blob> => {
  const path =
    kind === 'ar'
      ? `/api/v1/clients/${id}/statement/export`
      : `/api/v1/suppliers/${id}/statement/export`;
  const response = await apiClient.get(path, {
    params: { from, to, as_of, format },
    responseType: 'blob',
  });
  return response.data as Blob;
};

export const BUCKET_LABELS: ReadonlyArray<{ key: keyof CreditBuckets; label: string }> = [
  { key: 'current', label: 'Current' },
  { key: 'days_1_30', label: '1-30 days' },
  { key: 'days_31_60', label: '31-60 days' },
  { key: 'days_61_90', label: '61-90 days' },
  { key: 'days_90_plus', label: '90+ days' },
];

export const formatAed = (value: number): string =>
  value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
