import type { ArStatement } from '../../api/clients';
import {
  AGING_ROWS,
  OUTSTANDING_COPY,
  PDC_SUCCESS_NOTE,
} from '../../pages/statementHelpers';
import { formatAed } from '../../pages/quotationHelpers';
import styles from '../../pages/Quotations.module.css';
import { agingBucketAr } from './pdfChrome';
import { HtmlDualTitle, HtmlStackedLine } from './HtmlDualTitle';
import { PDF_LABELS } from './pdfLabels';
import { PDF_TITLES } from './pdfTitles';

type PreviewProps = {
  data: ArStatement;
  onClose: () => void;
};

export function StatementPdfPreview({ data, onClose }: PreviewProps) {
  return (
    <div className={styles.modalOverlay} data-testid="statement-pdf-preview">
      <div className={styles.pdfPreview}>
        <div className={styles.modalHeader}>
          <HtmlDualTitle
            en={PDF_TITLES.accountStatement.en}
            ar={PDF_TITLES.accountStatement.ar}
            enTestId="statement-pdf-title"
            arTestId="statement-pdf-title-ar"
            enAs="h3"
          />
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            data-testid="statement-pdf-preview-close"
          >
            &times;
          </button>
        </div>
        <HtmlStackedLine
          en={`Period: ${data.from}–${data.to}`}
          ar={PDF_LABELS.period.ar}
        />
        <HtmlStackedLine en={`As of: ${data.as_of}`} ar={PDF_LABELS.asOf.ar} />
        <HtmlStackedLine
          en={`Currency: ${data.currency || 'AED'}`}
          ar={PDF_LABELS.currency.ar}
        />
        <HtmlStackedLine
          testId="statement-pdf-billed"
          en={`Billed: ${formatAed(data.totals.billed)}`}
          ar={PDF_LABELS.billed.ar}
        />
        <HtmlStackedLine
          testId="statement-pdf-paid"
          en={`Paid (SUCCESS): ${formatAed(data.totals.paid)}`}
          ar={PDF_LABELS.paidSuccess.ar}
        />
        <HtmlStackedLine
          testId="statement-pdf-credited"
          en={`Credited (tax credit notes): ${formatAed(data.totals.credited)}`}
          ar={PDF_LABELS.creditedTaxCreditNotes.ar}
        />
        <HtmlStackedLine
          testId="statement-pdf-amount-due"
          en={`Amount due now: ${formatAed(data.amount_due_now)}`}
          ar={PDF_LABELS.amountDueNow.ar}
        />
        <HtmlStackedLine
          testId="statement-pdf-unapplied"
          en={`Unapplied credit: ${formatAed(data.credit_balance)}`}
          ar={PDF_LABELS.unappliedCredit.ar}
        />
        <p data-testid="statement-pdf-copy">{OUTSTANDING_COPY}</p>
        <p data-testid="statement-pdf-pdc-note">{PDC_SUCCESS_NOTE}</p>
        <div data-testid="statement-pdf-aging">
          {AGING_ROWS.map((row) => (
            <HtmlStackedLine
              key={row.key}
              en={`${row.label}: ${formatAed(data.aging.buckets[row.key])}`}
              ar={agingBucketAr(row.key)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
