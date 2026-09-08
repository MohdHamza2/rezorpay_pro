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
