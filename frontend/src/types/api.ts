export interface SuccessResponse<T> {
  success: true;
  data: T;
}

export interface ErrorResponse {
  success: false;
  error: {
    message: string;
    code?: string;
  };
}

export type ApiResponse<T> = SuccessResponse<T> | ErrorResponse;

export interface RevenueData {
  name: string;
  total: number;
}

export interface InvoiceStatusData {
  name: string;
  count: number;
}

export interface DashboardMetricsResponse {
  total_revenue: number;
  outstanding_balance: number;
  active_invoices: number;
  total_clients: number;
  revenue_overview: RevenueData[];
  invoice_status_distribution: InvoiceStatusData[];
}
