export interface SuccessResponse<T> {
  success: true;
  data: T;
}

export interface PaginationMeta {
  total: number;
  page: number;
  per_page: number;
  pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface PaginatedResponse<T> {
  success: true;
  data: T[];
  pagination: PaginationMeta;
}

export interface ErrorResponse {
  success: false;
  error: {
    message: string;
    code?: string;
    field?: string;
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
