import { z } from 'zod';
import type { ClientWritePayload } from '../api/clients';

export const PAYMENT_TERMS_DAYS = [0, 30, 45, 60] as const;
export type PaymentTermsDays = (typeof PAYMENT_TERMS_DAYS)[number];

export function isPaymentTermsDays(value: number): value is PaymentTermsDays {
  return (PAYMENT_TERMS_DAYS as readonly number[]).includes(value);
}

export const clientSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters'),
  email: z.string().email('Invalid email address'),
  phone: z.string().optional(),
  address: z.string().optional(),
  tax_id: z.string().optional(),
  credit_limit: z.string().refine((raw) => {
    const trimmed = raw.trim();
    if (trimmed === '') return true;
    const value = Number(trimmed);
    return Number.isFinite(value) && value >= 0;
  }, 'Blank inherits workspace default; 0 is COD'),
  payment_terms_days: z.number().refine(
    (value) => (PAYMENT_TERMS_DAYS as readonly number[]).includes(value),
    'Must be 0, 30, 45, or 60',
  ),
});

export type ClientFormValues = z.infer<typeof clientSchema>;

/** Empty string = inherit workspace default. `0` = COD. */
export function parseCreditLimitInput(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  return Number(trimmed);
}

function optionalText(value?: string): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

export function buildClientWritePayload(
  data: ClientFormValues,
  mode: 'create' | 'update',
): ClientWritePayload {
  const body: ClientWritePayload = {
    name: data.name,
    email: data.email,
    payment_terms_days: data.payment_terms_days,
  };
  const phone = optionalText(data.phone);
  const address = optionalText(data.address);
  const taxId = optionalText(data.tax_id);
  if (phone) body.phone = phone;
  if (address) body.address = address;
  if (taxId) body.tax_id = taxId;
  const limit = parseCreditLimitInput(data.credit_limit);
  if (mode === 'update' || limit !== null) body.credit_limit = limit;
  return body;
}

export function creditLimitFieldValue(limit: number | string | null | undefined): string {
  if (limit == null || limit === '') return '';
  return String(limit);
}
