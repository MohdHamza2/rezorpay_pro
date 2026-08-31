import type { Client } from '../../api/clients';
import type { DeliveryNote } from '../../api/deliveryNotes';
import type { Workspace } from '../../api/workspaces';
import styles from '../../pages/Quotations.module.css';

function formatQty(value: string | number | null | undefined): string {
  return Number(value ?? 0).toFixed(2);
}

type PreviewProps = {
  dn: DeliveryNote;
  client?: Client;
  workspace?: Workspace;
  lpoNumber?: string;
  invoiceNumber?: string;
  onClose: () => void;
};

export function DeliveryNotePdfPreview({
  dn,
  client,
  workspace,
  lpoNumber,
  invoiceNumber,
  onClose,
}: PreviewProps) {
  const sellerTrn = (workspace?.trn ?? '').trim();
  const sellerAddress = (workspace?.address ?? '').trim();
  return (
    <div className={styles.modalOverlay} data-testid="dn-pdf-preview">
      <div className={styles.pdfPreview}>
        <div className={styles.modalHeader}>
          <h3 data-testid="dn-pdf-title">Delivery Note</h3>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            data-testid="dn-pdf-preview-close"
          >
            &times;
          </button>
        </div>
        <p>DN No: {dn.dn_number}</p>
        {lpoNumber ? <p>LPO No: {lpoNumber}</p> : null}
        {invoiceNumber ? <p>Invoice No: {invoiceNumber}</p> : null}
        <p>Delivery Date: {dn.delivery_date}</p>
        <p>Customer: {client?.name || '—'}</p>
        {sellerTrn ? <p>TRN: {sellerTrn}</p> : null}
        {sellerAddress ? <p>{sellerAddress}</p> : null}
        {(dn.items ?? []).map((item) => (
          <p key={item.id}>
            {item.sku_snapshot ? `${item.sku_snapshot} — ` : ''}
            {item.description}: {formatQty(item.quantity)}
          </p>
        ))}
      </div>
    </div>
  );
}
