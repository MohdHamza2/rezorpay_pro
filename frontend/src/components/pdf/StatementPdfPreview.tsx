import type { ArStatement } from '../../api/clients';
import {
  AGING_ROWS,
  OUTSTANDING_COPY,
  PDC_SUCCESS_NOTE,
} from '../../pages/statementHelpers';
import { formatAed } from '../../pages/quotationHelpers';
import styles from '../../pages/Quotations.module.css';

type PreviewProps = {
  data: ArStatement;
  onClose: () => void;
};

export function StatementPdfPreview({ data, onClose }: PreviewProps) {
  return (
    <div className={styles.modalOverlay} data-testid="statement-pdf-preview">
      <div className={styles.pdfPreview}>
        <div className={styles.modalHeader}>
          <h3 data-testid="statement-pdf-title">Account Statement</h3>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            data-testid="statement-pdf-preview-close"
          >
            &times;
          </button>
        </div>
        <p>
          Period: {data.from}–{data.to}
        </p>
        <p>As of: {data.as_of}</p>
        <p>Currency: {data.currency || 'AED'}</p>
        <p data-testid="statement-pdf-billed">Billed: {formatAed(data.totals.billed)}</p>
        <p data-testid="statement-pdf-paid">Paid (SUCCESS): {formatAed(data.totals.paid)}</p>
        <p data-testid="statement-pdf-credited">
          Credited (tax credit notes): {formatAed(data.totals.credited)}
        </p>
        <p data-testid="statement-pdf-amount-due">Amount due now: {formatAed(data.amount_due_now)}</p>
        <p data-testid="statement-pdf-unapplied">
          Unapplied credit: {formatAed(data.credit_balance)}
        </p>
        <p data-testid="statement-pdf-copy">{OUTSTANDING_COPY}</p>
        <p data-testid="statement-pdf-pdc-note">{PDC_SUCCESS_NOTE}</p>
        <div data-testid="statement-pdf-aging">
          {AGING_ROWS.map((row) => (
            <p key={row.key}>
              {row.label}: {formatAed(data.aging.buckets[row.key])}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}
