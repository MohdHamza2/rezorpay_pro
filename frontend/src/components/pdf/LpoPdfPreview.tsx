import type { Client } from '../../api/clients';
import type { CustomerPurchaseOrder } from '../../api/lpos';
import type { Workspace } from '../../api/workspaces';
import styles from '../../pages/Quotations.module.css';

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
          <h3 data-testid="lpo-pdf-title">LPO</h3>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            data-testid="lpo-pdf-preview-close"
          >
            &times;
          </button>
        </div>
        <p>LPO No: {lpo.lpo_number}</p>
        {lpo.customer_po_number ? <p>Customer PO: {lpo.customer_po_number}</p> : null}
        {quotationNumber ? <p>Quote No: {quotationNumber}</p> : null}
        <p>LPO Date: {lpo.lpo_date}</p>
        <p>Customer: {client?.name || '—'}</p>
        {sellerTrn ? <p>TRN: {sellerTrn}</p> : null}
        {sellerAddress ? <p>{sellerAddress}</p> : null}
      </div>
    </div>
  );
}
