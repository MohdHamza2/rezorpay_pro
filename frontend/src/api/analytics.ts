import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export type AnalyticsInterval = 'day' | 'week' | 'month';

export interface RevenueRow {
  period: string;
  invoice_count: number;
  subtotal: number;
  tax_amount: number;
  total_amount: number;
}

export interface RevenueReport {
  from: string;
  to: string;
  interval: AnalyticsInterval;
  currency: string;
  rows: RevenueRow[];
}

export interface SalesByCustomerRow {
  client_id: string;
  client_name: string;
  invoice_count: number;
  subtotal: number;
  tax_amount: number;
  total_amount: number;
}

export interface SalesByCustomerReport {
  from: string;
  to: string;
  currency: string;
  rows: SalesByCustomerRow[];
}

export interface SalesByProductRow {
  product_id: string | null;
  product_name: string;
  sku: string;
  quantity: number;
  line_net: number;
  tax_amount: number;
  total_price: number;
}

export interface SalesByProductReport {
  from: string;
  to: string;
  currency: string;
  rows: SalesByProductRow[];
}

export interface CashflowRow {
  period: string;
  inflows: number;
  outflows: number;
  net: number;
}

export interface CashflowReport {
  from: string;
  to: string;
  interval: AnalyticsInterval;
  currency: string;
  rows: CashflowRow[];
}

const toRevenueRows = (rows: RevenueRow[]): RevenueRow[] =>
  rows.map((row) => ({
    ...row,
    subtotal: Number(row.subtotal),
    tax_amount: Number(row.tax_amount),
    total_amount: Number(row.total_amount),
  }));

const toCustomerRows = (rows: SalesByCustomerRow[]): SalesByCustomerRow[] =>
  rows.map((row) => ({
    ...row,
    subtotal: Number(row.subtotal),
    tax_amount: Number(row.tax_amount),
    total_amount: Number(row.total_amount),
  }));

const toProductRows = (rows: SalesByProductRow[]): SalesByProductRow[] =>
  rows.map((row) => ({
    ...row,
    quantity: Number(row.quantity),
    line_net: Number(row.line_net),
    tax_amount: Number(row.tax_amount),
    total_price: Number(row.total_price),
  }));

const toCashflowRows = (rows: CashflowRow[]): CashflowRow[] =>
  rows.map((row) => ({
    ...row,
    inflows: Number(row.inflows),
    outflows: Number(row.outflows),
    net: Number(row.net),
  }));

export const getRevenue = async (
  from: string,
  to: string,
  interval: AnalyticsInterval
): Promise<RevenueReport> => {
  const response = await apiClient.get<SuccessResponse<RevenueReport>>(
    '/api/v1/reports/analytics/revenue',
    { params: { from, to, interval } }
  );
  return { ...response.data.data, rows: toRevenueRows(response.data.data.rows) };
};

export const getSalesByCustomer = async (
  from: string,
  to: string
): Promise<SalesByCustomerReport> => {
  const response = await apiClient.get<SuccessResponse<SalesByCustomerReport>>(
    '/api/v1/reports/analytics/sales-by-customer',
    { params: { from, to } }
  );
  return {
    ...response.data.data,
    rows: toCustomerRows(response.data.data.rows),
  };
};

export const getSalesByProduct = async (
  from: string,
  to: string
): Promise<SalesByProductReport> => {
  const response = await apiClient.get<SuccessResponse<SalesByProductReport>>(
    '/api/v1/reports/analytics/sales-by-product',
    { params: { from, to } }
  );
  return {
    ...response.data.data,
    rows: toProductRows(response.data.data.rows),
  };
};

export const getCashflow = async (
  from: string,
  to: string,
  interval: AnalyticsInterval
): Promise<CashflowReport> => {
  const response = await apiClient.get<SuccessResponse<CashflowReport>>(
    '/api/v1/reports/analytics/cashflow',
    { params: { from, to, interval } }
  );
  return { ...response.data.data, rows: toCashflowRows(response.data.data.rows) };
};
