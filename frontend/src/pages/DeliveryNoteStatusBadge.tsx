import type { DeliveryNoteStatus } from '../api/deliveryNotes';
import quoteStyles from './Quotations.module.css';
import styles from './DeliveryNotes.module.css';

const BADGE: Record<DeliveryNoteStatus, string> = {
  DRAFT: quoteStyles.badgeDraft,
  CONFIRMED: styles.badgeConfirmed,
  CANCELLED: styles.badgeCancelled,
};

export function DeliveryNoteStatusBadge({ status }: { status: DeliveryNoteStatus }) {
  return (
    <span className={`${quoteStyles.badge} ${BADGE[status]}`} data-testid="dn-status">
      {status}
    </span>
  );
}
