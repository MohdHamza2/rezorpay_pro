import { z } from 'zod';
import type { CreditBuckets, StatementDocType } from '../api/clients';
import { todayIso } from './quotationHelpers';

export type StatementRange = {
  from: string;
  to: string;
  as_of: string;
};

export const AGING_ROWS: { key: keyof CreditBuckets; label: string }[] = [
  { key: 'current', label: 'Current' },
  { key: 'days_1_30', label: '1–30' },
  { key: 'days_31_60', label: '31–60' },
  { key: 'days_61_90', label: '61–90' },
  { key: 'days_90_plus', label: '90+' },
];

export const PDC_SUCCESS_NOTE =
  'PDC recorded as SUCCESS reduces outstanding until bounce/clear (later wave).';

export const OUTSTANDING_COPY =
  'Outstanding amounts are current; aging days vs as-of.';

export function defaultStatementRange(): StatementRange {
  const to = todayIso();
  return { from: `${to.slice(0, 7)}-01`, to, as_of: to };
}

export const statementRangeSchema = z
  .object({
    from: z.string().min(1, 'From is required'),
    to: z.string().min(1, 'To is required'),
    as_of: z.string().min(1, 'As of is required'),
  })
  .superRefine((value, ctx) => {
    if (value.from > value.to) {
      ctx.addIssue({ code: 'custom', message: 'From must be on or before to', path: ['from'] });
    }
    if (value.as_of > todayIso()) {
      ctx.addIssue({ code: 'custom', message: 'As of cannot be after today', path: ['as_of'] });
    }
  });

export function formatMoney(value: string | number | null | undefined): string {
  return Number(value ?? 0).toFixed(2);
}

export function retryUnlessClientError(count: number, error: unknown): boolean {
  const status = (error as { response?: { status?: number } }).response?.status;
  if (status && status < 500) return false;
  return count < 2;
}

export function isPaymentLine(docType: StatementDocType): boolean {
  return docType === 'PAYMENT';
}

export function isCreditNoteLine(docType: StatementDocType): boolean {
  return docType === 'TAX_CREDIT_NOTE';
}

export function isPendingLine(docType: StatementDocType): boolean {
  return docType === 'PAYMENT_PENDING';
}
