import type { QuotationStatus } from '../api/quotations';
import styles from './Quotations.module.css';

const BADGE: Record<QuotationStatus, string> = {
  DRAFT: styles.badgeDraft,
  SENT: styles.badgeSent,
  ACCEPTED: styles.badgeAccepted,
  REJECTED: styles.badgeRejected,
  EXPIRED: styles.badgeExpired,
  CONVERTED: styles.badgeConverted,
};

export function QuotationStatusBadge({ status }: { status: QuotationStatus }) {
  return (
    <span className={`${styles.badge} ${BADGE[status]}`} data-testid="quotation-status">
      {status}
    </span>
  );
}
