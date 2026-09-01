import type { CreditNoteStatus } from '../api/creditNotes';
import quoteStyles from './Quotations.module.css';
import styles from './CreditNotes.module.css';

const BADGE: Record<CreditNoteStatus, string> = {
  DRAFT: quoteStyles.badgeDraft,
  ISSUED: styles.badgeIssued,
};

export function CreditNoteStatusBadge({ status }: { status: CreditNoteStatus }) {
  return (
    <span className={`${quoteStyles.badge} ${BADGE[status]}`} data-testid="cn-status">
      {status}
    </span>
  );
}
