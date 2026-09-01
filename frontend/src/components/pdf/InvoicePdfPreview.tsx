import type { Client } from '../../api/clients';
import type { Invoice } from '../../api/invoices';
import type { Workspace } from '../../api/workspaces';
import styles from '../../pages/Invoices.module.css';
import { HtmlDualTitle, HtmlStackedLine } from './HtmlDualTitle';
import { snapOrLive } from './invoicePdfFields';
import { PDF_LABELS } from './pdfLabels';
import { PDF_TITLES } from './pdfTitles';

type PreviewProps = {
  invoice: Invoice;
  client?: Client;
  workspace?: Workspace;
  onClose: () => void;
};

export function InvoicePdfPreview({ invoice, client, workspace, onClose }: PreviewProps) {
  const sellerTrn = snapOrLive(invoice.status, invoice.seller_trn_snapshot, workspace?.trn);
  const sellerAddress = snapOrLive(
    invoice.status,
    invoice.seller_address_snapshot,
    workspace?.address,
  );
  const buyerName = snapOrLive(invoice.status, invoice.buyer_name_snapshot, client?.name);
  return (
    <div className={styles.modalOverlay} data-testid="pdf-preview">
      <div className={styles.pdfPreview}>
        <div className={styles.modalHeader}>
          <HtmlDualTitle
            en={PDF_TITLES.taxInvoice.en}
            ar={PDF_TITLES.taxInvoice.ar}
            enTestId="pdf-title"
            arTestId="pdf-title-ar"
            enAs="h3"
          />
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            data-testid="pdf-preview-close"
          >
            &times;
          </button>
        </div>
        <HtmlStackedLine
          testId="pdf-seller-trn"
          en={`TRN: ${sellerTrn || '—'}`}
          ar={PDF_LABELS.trn.ar}
        />
        {sellerAddress ? <p data-testid="pdf-seller-address">{sellerAddress}</p> : null}
        <HtmlStackedLine en={`Bill to: ${buyerName || '—'}`} ar={PDF_LABELS.billTo.ar} />
        <HtmlStackedLine
          en={`Invoice No: ${invoice.invoice_number}`}
          ar={PDF_LABELS.invoiceNo.ar}
        />
        <HtmlStackedLine
          en={`Supply Date: ${invoice.supply_date || invoice.issue_date}`}
          ar={PDF_LABELS.supplyDate.ar}
        />
      </div>
    </div>
  );
}
