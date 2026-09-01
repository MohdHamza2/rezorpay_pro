import type { Payment, PdcAction } from '../api/invoices';
import type { UserRole } from '../types/auth';

export const PDC_ACTION_LABEL: Record<PdcAction, string> = {
  deposit: 'Deposit',
  clear: 'Clear',
  bounce: 'Bounce',
  return: 'Return',
};

export function canManagePdc(role?: UserRole | string): boolean {
  return role === 'OWNER' || role === 'ADMIN';
}

export function isUnclearedPdc(payment: Payment): boolean {
  return payment.payment_method === 'PDC' && payment.status === 'PENDING';
}

export function isPdcCash(payment: Payment): boolean {
  return (
    payment.payment_method === 'PDC' &&
    (payment.status === 'SUCCESS' || payment.pdc_status === 'CLEARED')
  );
}

export function legalPdcActions(payment: Payment): PdcAction[] {
  if (payment.payment_method !== 'PDC') return [];
  if (isPdcCash(payment)) return [];
  if (payment.status !== 'PENDING') return [];
  if (payment.pdc_status === 'RECEIVED') return ['deposit', 'return'];
  if (payment.pdc_status === 'DEPOSITED') return ['clear', 'bounce'];
  return [];
}

export function paymentRecordedMessage(payment: Payment): string {
  if (isUnclearedPdc(payment)) {
    return 'PDC recorded as pending — not cash until cleared';
  }
  return 'Payment recorded';
}

export function pdcActionMessage(action: PdcAction): string {
  if (action === 'deposit') return 'PDC deposited — still pending until cleared';
  if (action === 'clear') return 'PDC cleared — now cash';
  if (action === 'bounce') return 'PDC bounced — invoice still open';
  return 'PDC returned — not cash';
}
