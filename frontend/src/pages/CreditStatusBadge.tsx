import type { CreditStatus } from '../api/clients';
import styles from './Clients.module.css';

const BADGE: Record<CreditStatus, string> = {
  ACTIVE: styles.badgeActive,
  WARNING: styles.badgeWarning,
  HOLD: styles.badgeHold,
};

export function CreditStatusBadge({ status }: { status?: CreditStatus }) {
  const value = status ?? 'ACTIVE';
  return (
    <span className={`${styles.badge} ${BADGE[value]}`} data-testid="client-credit-status">
      {value}
    </span>
  );
}
