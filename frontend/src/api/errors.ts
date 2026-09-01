import type { AxiosError } from 'axios';

export type ApiErrorInfo = {
  code?: string;
  message: string;
  field?: string;
};

type PydanticDetail = { msg?: string };

type ErrorBody = {
  error?: {
    code?: string;
    message?: string;
    field?: string;
    details?: PydanticDetail[];
  };
  detail?: string | PydanticDetail[];
};

function firstDetailMessage(details?: PydanticDetail[]): string | undefined {
  const msg = details?.[0]?.msg;
  return typeof msg === 'string' && msg ? msg : undefined;
}

function stringDetail(detail: ErrorBody['detail']): string | undefined {
  if (typeof detail === 'string' && detail) return detail;
  return undefined;
}

/** Handlers toast these; interceptor must not duplicate. */
export const HANDLED_TOAST_CODES = new Set(['FTA_SEND_BLOCKED', 'CREDIT_HOLD']);

const CODE_PREFIX_TOASTS = new Set([
  'DATE_RANGE_TOO_LONG',
  'STATEMENT_TOO_LARGE',
  'NO_LIST_PRICE',
]);

export function formatErrorToast(info: ApiErrorInfo): string {
  if (info.code && CODE_PREFIX_TOASTS.has(info.code)) {
    return `${info.code}: ${info.message}`;
  }
  if (info.code === 'VALIDATION_ERROR' && info.field === 'product_id') {
    return `${info.code}: ${info.message}`;
  }
  return info.message;
}

export function extractApiError(error: unknown): ApiErrorInfo {
  const data = (error as AxiosError<ErrorBody>).response?.data;
  const body = data?.error;
  const detail = stringDetail(data?.detail);
  if (!body) return { message: detail || 'An error occurred' };
  return {
    code: body.code,
    field: body.field,
    message: body.message || firstDetailMessage(body.details) || detail || 'An error occurred',
  };
}

export function skipInterceptorToast(code?: string): boolean {
  return Boolean(code && HANDLED_TOAST_CODES.has(code));
}

/** WP-A DN isolation uses HTTP 404; wrapper code may be HTTP_ERROR, not NOT_FOUND. */
export function isHttpNotFound(error: unknown): boolean {
  return (error as AxiosError).response?.status === 404;
}
