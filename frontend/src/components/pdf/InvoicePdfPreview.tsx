import type { Client } from '../../api/clients';
import type { Invoice } from '../../api/invoices';
import type { Workspace } from '../../api/workspaces';
import styles from '../../pages/Invoices.module.css';
import { snapOrLive } from './invoicePdfFields';

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
          <h3 data-testid="pdf-title">Tax Invoice</h3>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            data-testid="pdf-preview-close"
          >
            &times;
          </button>
        </div>
        <p data-testid="pdf-seller-trn">TRN: {sellerTrn || '—'}</p>
        {sellerAddress ? <p data-testid="pdf-seller-address">{sellerAddress}</p> : null}
        <p>Bill to: {buyerName || '—'}</p>
        <p>Invoice No: {invoice.invoice_number}</p>
        <p>Supply Date: {invoice.supply_date || invoice.issue_date}</p>
      </div>
    </div>
  );
}
