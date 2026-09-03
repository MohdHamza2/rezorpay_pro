import type { TaxDebitNoteStatus } from '../api/debitNotes';
import quoteStyles from './Quotations.module.css';
import styles from './DebitNotes.module.css';

const BADGE: Record<TaxDebitNoteStatus, string> = {
  DRAFT: quoteStyles.badgeDraft,
  ISSUED: styles.badgeIssued,
};

export function DebitNoteStatusBadge({ status }: { status: TaxDebitNoteStatus }) {
  return (
    <span className={`${quoteStyles.badge} ${BADGE[status]}`} data-testid="tdn-status">
      {status}
    </span>
  );
}
