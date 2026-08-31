import type { InvoiceStatus } from '../../api/invoices';

export function snapOrLive(
  status: InvoiceStatus,
  snapshot: string | null | undefined,
  live: string | null | undefined,
): string {
  if (status !== 'DRAFT' && snapshot != null && String(snapshot).trim() !== '') {
    return String(snapshot).trim();
  }
  return (live ?? '').trim();
}
