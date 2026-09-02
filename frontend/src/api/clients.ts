import { apiClient } from './client';
import type { SuccessResponse } from '../types/api';

export type CreditStatus = 'ACTIVE' | 'WARNING' | 'HOLD';

export interface CreditBuckets {
  current: number | string;
  days_1_30: number | string;
  days_31_60: number | string;
  days_61_90: number | string;
  days_90_plus: number | string;
}

export interface ClientCredit {
  credit_status: CreditStatus;
  credit_limit: number | string | null;
  effective_credit_limit: number | string;
  payment_terms_days: number;
  exposure: number | string;
  oldest_overdue_days: number | null;
  buckets: CreditBuckets;
  credit_balance?: number | string | null;
}

/** GET/list row. Do not POST/PUT this shape — extra keys 422. */
export interface Client {
  id: string;
  name: string;
  email: string;
  address?: string | null;
  phone?: string;
  tax_id?: string | null;
  credit_limit?: number | string | null;
  payment_terms_days?: number;
  credit_status?: CreditStatus;
  effective_credit_limit?: number | string;
  exposure?: number | string;
  credit_balance?: number | string | null;
  created_at: string;
}

/** WP-A ClientCreate/ClientUpdate only (`extra="forbid"`). */
export interface ClientWritePayload {
  name: string;
  email?: string;
  phone?: string;
  address?: string;
  tax_id?: string;
  credit_limit?: number | null;
  payment_terms_days?: number;
}

export const getClients = async (): Promise<Client[]> => {
  const response = await apiClient.get<SuccessResponse<Client[]>>('/api/v1/clients');
  return response.data.data;
};

export const getClientCredit = async (id: string): Promise<ClientCredit> => {
  const response = await apiClient.get<SuccessResponse<ClientCredit>>(
    `/api/v1/clients/${id}/credit`,
  );
  return response.data.data;
};

export type StatementDocType =
  | 'OPENING'
  | 'TAX_INVOICE'
  | 'PAYMENT'
  | 'PAYMENT_PENDING'
  | 'TAX_CREDIT_NOTE'
  | 'TAX_DEBIT_NOTE';

export type ArStatementQuery = {
  from: string;
  to: string;
  as_of?: string;
};

export interface ArStatementParty {
  id?: string;
  name: string;
  tax_id?: string | null;
  trn?: string | null;
  address?: string | null;
}

export interface ArStatementLine {
  date: string;
  doc_type: StatementDocType;
  doc_type_label: string;
  number: string | null;
  reference: string | null;
  payment_method: string | null;
  payment_status: string | null;
  cleared_cash: boolean | null;
  pending_amount: number | string;
  debit: number | string;
  credit: number | string;
  running_balance: number | string;
}

export interface ArStatementTotals {
  billed: number | string;
  paid: number | string;
  credited: number | string;
  debited?: number | string;
  pending: number | string;
  closing_running: number | string;
}

export interface ArStatementAging {
  as_of: string;
  buckets: CreditBuckets;
}

export interface ArStatement {
  client: ArStatementParty;
  workspace: ArStatementParty;
  currency: string;
  from: string;
  to: string;
  as_of: string;
  opening_balance: number | string;
  lines: ArStatementLine[];
  totals: ArStatementTotals;
  amount_due_now: number | string;
  credit_balance: number | string;
  aging: ArStatementAging;
}

export const getArStatement = async (
  clientId: string,
  query: ArStatementQuery,
): Promise<ArStatement> => {
  const params: ArStatementQuery = { from: query.from, to: query.to };
  if (query.as_of) params.as_of = query.as_of;
  const response = await apiClient.get<SuccessResponse<ArStatement>>(
    `/api/v1/clients/${clientId}/ar-statement`,
    { params },
  );
  return response.data.data;
};

export const createClient = async (data: ClientWritePayload): Promise<Client> => {
  const response = await apiClient.post<SuccessResponse<Client>>('/api/v1/clients', data);
  return response.data.data;
};

export const updateClient = async (id: string, data: ClientWritePayload): Promise<Client> => {
  const response = await apiClient.put<SuccessResponse<Client>>(`/api/v1/clients/${id}`, data);
  return response.data.data;
};

export const deleteClient = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/v1/clients/${id}`);
};
