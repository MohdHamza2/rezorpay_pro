import type { Client } from '../../api/clients';
import type { DeliveryNote } from '../../api/deliveryNotes';
import type { Workspace } from '../../api/workspaces';
import styles from '../../pages/Quotations.module.css';
import { HtmlDualTitle, HtmlStackedLine } from './HtmlDualTitle';
import { PDF_LABELS } from './pdfLabels';
import { PDF_TITLES } from './pdfTitles';

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
          <HtmlDualTitle
            en={PDF_TITLES.deliveryNote.en}
            ar={PDF_TITLES.deliveryNote.ar}
            enTestId="dn-pdf-title"
            arTestId="dn-pdf-title-ar"
            enAs="h3"
          />
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            data-testid="dn-pdf-preview-close"
          >
            &times;
          </button>
        </div>
        <HtmlStackedLine en={`DN No: ${dn.dn_number}`} ar={PDF_LABELS.dnNo.ar} />
        {lpoNumber ? (
          <HtmlStackedLine en={`LPO No: ${lpoNumber}`} ar={PDF_LABELS.lpoNo.ar} />
        ) : null}
        {invoiceNumber ? (
          <HtmlStackedLine en={`Invoice No: ${invoiceNumber}`} ar={PDF_LABELS.invoiceNo.ar} />
        ) : null}
        <HtmlStackedLine
          en={`Delivery Date: ${dn.delivery_date}`}
          ar={PDF_LABELS.deliveryDate.ar}
        />
        <HtmlStackedLine en={`Customer: ${client?.name || '—'}`} ar={PDF_LABELS.customer.ar} />
        {sellerTrn ? <HtmlStackedLine en={`TRN: ${sellerTrn}`} ar={PDF_LABELS.trn.ar} /> : null}
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
