import type { Client } from '../../api/clients';
import type { CreditNote } from '../../api/creditNotes';
import type { Invoice } from '../../api/invoices';
import type { Workspace } from '../../api/workspaces';
import styles from '../../pages/Quotations.module.css';
import { HtmlDualTitle, HtmlStackedLine } from './HtmlDualTitle';
import { PDF_LABELS } from './pdfLabels';
import { PDF_TITLES } from './pdfTitles';

function money(value: string | number | null | undefined): string {
  return Number(value ?? 0).toFixed(2);
}

function snapFirst(snapshot: string | null | undefined, live: string | null | undefined): string {
  const frozen = (snapshot ?? '').trim();
  if (frozen) return frozen;
  return (live ?? '').trim();
}

type PreviewProps = {
  cn: CreditNote;
  client?: Client;
  workspace?: Workspace;
  invoice?: Invoice;
  onClose: () => void;
};

export function CreditNotePdfPreview({
  cn,
  client,
  workspace,
  invoice,
  onClose,
}: PreviewProps) {
  const sellerTrn = snapFirst(cn.seller_trn_snapshot, workspace?.trn);
  const sellerAddress = snapFirst(cn.seller_address_snapshot, workspace?.address);
  const buyerTrn = snapFirst(cn.buyer_trn_snapshot, client?.tax_id);
  const originalNumber = cn.original_invoice_number || invoice?.invoice_number || '—';
  const originalDate = cn.original_issue_date || invoice?.issue_date || '—';
  return (
    <div className={styles.modalOverlay} data-testid="cn-pdf-preview">
      <div className={styles.pdfPreview}>
        <div className={styles.modalHeader}>
          <HtmlDualTitle
            en={PDF_TITLES.taxCreditNote.en}
            ar={PDF_TITLES.taxCreditNote.ar}
            enTestId="cn-pdf-title"
            arTestId="cn-pdf-title-ar"
            enAs="h3"
          />
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            data-testid="cn-pdf-preview-close"
          >
            &times;
          </button>
        </div>
        <HtmlStackedLine
          en={`Credit Note No: ${cn.credit_note_number}`}
          ar={PDF_LABELS.creditNoteNo.ar}
        />
        <HtmlStackedLine en={`Issue Date: ${cn.issue_date}`} ar={PDF_LABELS.issueDate.ar} />
        <HtmlStackedLine
          testId="cn-pdf-original-invoice"
          en={`Original Invoice: ${originalNumber}`}
          ar={PDF_LABELS.originalInvoice.ar}
        />
        <HtmlStackedLine
          en={`Original Issue Date: ${originalDate}`}
          ar={PDF_LABELS.originalIssueDate.ar}
        />
        <HtmlStackedLine
          testId="cn-pdf-seller-trn"
          en={`Seller TRN: ${sellerTrn || '—'}`}
          ar={PDF_LABELS.trn.ar}
        />
        {sellerAddress ? <p>{sellerAddress}</p> : null}
        <HtmlStackedLine
          testId="cn-pdf-buyer-trn"
          en={`Buyer TRN: ${buyerTrn || '—'}`}
          ar={PDF_LABELS.trn.ar}
        />
        <HtmlStackedLine
          en={`Credit to: ${snapFirst(cn.buyer_name_snapshot, client?.name) || '—'}`}
          ar={PDF_LABELS.creditTo.ar}
        />
        <HtmlStackedLine
          en={`Credit total: AED ${money(cn.total_amount)}`}
          ar={PDF_LABELS.creditTotalAed.ar}
        />
      </div>
    </div>
  );
}
