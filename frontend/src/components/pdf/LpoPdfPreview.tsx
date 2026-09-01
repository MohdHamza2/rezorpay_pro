import type { Client } from '../../api/clients';
import type { CustomerPurchaseOrder } from '../../api/lpos';
import type { Workspace } from '../../api/workspaces';
import styles from '../../pages/Quotations.module.css';
import { HtmlDualTitle, HtmlStackedLine } from './HtmlDualTitle';
import { PDF_LABELS } from './pdfLabels';
import { PDF_TITLES } from './pdfTitles';

type PreviewProps = {
  lpo: CustomerPurchaseOrder;
  client?: Client;
  workspace?: Workspace;
  quotationNumber?: string;
  onClose: () => void;
};

export function LpoPdfPreview({
  lpo,
  client,
  workspace,
  quotationNumber,
  onClose,
}: PreviewProps) {
  const sellerTrn = (workspace?.trn ?? '').trim();
  const sellerAddress = (workspace?.address ?? '').trim();
  return (
    <div className={styles.modalOverlay} data-testid="lpo-pdf-preview">
      <div className={styles.pdfPreview}>
        <div className={styles.modalHeader}>
          <HtmlDualTitle
            en={PDF_TITLES.lpo.en}
            ar={PDF_TITLES.lpo.ar}
            enTestId="lpo-pdf-title"
            arTestId="lpo-pdf-title-ar"
            enAs="h3"
          />
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            data-testid="lpo-pdf-preview-close"
          >
            &times;
          </button>
        </div>
        <HtmlStackedLine en={`LPO No: ${lpo.lpo_number}`} ar={PDF_LABELS.lpoNo.ar} />
        {lpo.customer_po_number ? (
          <HtmlStackedLine
            en={`Customer PO: ${lpo.customer_po_number}`}
            ar={PDF_LABELS.customerPo.ar}
          />
        ) : null}
        {quotationNumber ? (
          <HtmlStackedLine en={`Quote No: ${quotationNumber}`} ar={PDF_LABELS.quoteNo.ar} />
        ) : null}
        <HtmlStackedLine en={`LPO Date: ${lpo.lpo_date}`} ar={PDF_LABELS.lpoDate.ar} />
        <HtmlStackedLine en={`Customer: ${client?.name || '—'}`} ar={PDF_LABELS.customer.ar} />
        {sellerTrn ? <HtmlStackedLine en={`TRN: ${sellerTrn}`} ar={PDF_LABELS.trn.ar} /> : null}
        {sellerAddress ? <p>{sellerAddress}</p> : null}
      </div>
    </div>
  );
}
