import type { Client } from '../../api/clients';
import type { Quotation } from '../../api/quotations';
import type { Workspace } from '../../api/workspaces';
import styles from '../../pages/Quotations.module.css';

type PreviewProps = {
  quotation: Quotation;
  client?: Client;
  workspace?: Workspace;
  onClose: () => void;
};

export function QuotationPdfPreview({ quotation, client, workspace, onClose }: PreviewProps) {
  const sellerTrn = (workspace?.trn ?? '').trim();
  const sellerAddress = (workspace?.address ?? '').trim();
  return (
    <div className={styles.modalOverlay} data-testid="quotation-pdf-preview">
      <div className={styles.pdfPreview}>
        <div className={styles.modalHeader}>
          <h3 data-testid="quotation-pdf-title">Quotation</h3>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            data-testid="quotation-pdf-preview-close"
          >
            &times;
          </button>
        </div>
        <p>Quote No: {quotation.quotation_number}</p>
        <p>Valid Until: {quotation.valid_until}</p>
        <p>Quote to: {client?.name || '—'}</p>
        {sellerTrn ? <p>TRN: {sellerTrn}</p> : null}
        {sellerAddress ? <p>{sellerAddress}</p> : null}
      </div>
    </div>
  );
}
