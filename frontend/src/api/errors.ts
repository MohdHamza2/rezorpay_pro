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

export function extractApiError(error: unknown): ApiErrorInfo {
  const body = (error as AxiosError<ErrorBody>).response?.data?.error;
  if (!body) return { message: 'An error occurred' };
  return {
    code: body.code,
    field: body.field,
    message: body.message || firstDetailMessage(body.details) || 'An error occurred',
  };
}
