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
};

function firstDetailMessage(details?: PydanticDetail[]): string | undefined {
  const msg = details?.[0]?.msg;
  return typeof msg === 'string' && msg ? msg : undefined;
}

/** Handlers toast these; interceptor must not duplicate. */
export const HANDLED_TOAST_CODES = new Set(['FTA_SEND_BLOCKED', 'CREDIT_HOLD']);

const STATEMENT_TOAST_CODES = new Set(['DATE_RANGE_TOO_LONG', 'STATEMENT_TOO_LARGE']);

export function formatErrorToast(info: ApiErrorInfo): string {
  if (info.code && STATEMENT_TOAST_CODES.has(info.code)) {
    return `${info.code}: ${info.message}`;
  }
  return info.message;
}

export function extractApiError(error: unknown): ApiErrorInfo {
  const body = (error as AxiosError<ErrorBody>).response?.data?.error;
  if (!body) return { message: 'An error occurred' };
  return {
    code: body.code,
    field: body.field,
    message: body.message || firstDetailMessage(body.details) || 'An error occurred',
  };
}

export function skipInterceptorToast(code?: string): boolean {
  return Boolean(code && HANDLED_TOAST_CODES.has(code));
}

/** WP-A DN isolation uses HTTP 404; wrapper code may be HTTP_ERROR, not NOT_FOUND. */
export function isHttpNotFound(error: unknown): boolean {
  return (error as AxiosError).response?.status === 404;
}
