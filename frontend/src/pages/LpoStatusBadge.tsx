import type { LpoStatus } from '../api/lpos';
import quoteStyles from './Quotations.module.css';
import styles from './Lpos.module.css';

const BADGE: Record<LpoStatus, string> = {
  DRAFT: quoteStyles.badgeDraft,
  RECEIVED: styles.badgeReceived,
  PARTIAL: styles.badgePartial,
  INVOICED: styles.badgeInvoiced,
  CANCELLED: styles.badgeCancelled,
};

export function LpoStatusBadge({ status }: { status: LpoStatus }) {
  return (
    <span className={`${quoteStyles.badge} ${BADGE[status]}`} data-testid="lpo-status">
      {status}
    </span>
  );
}
