import type { Client } from '../../api/clients';
import type { Quotation } from '../../api/quotations';
import type { Workspace } from '../../api/workspaces';
import styles from '../../pages/Quotations.module.css';
import { HtmlDualTitle, HtmlStackedLine } from './HtmlDualTitle';
import { PDF_LABELS } from './pdfLabels';
import { PDF_TITLES } from './pdfTitles';

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
          <HtmlDualTitle
            en={PDF_TITLES.quotation.en}
            ar={PDF_TITLES.quotation.ar}
            enTestId="quotation-pdf-title"
            arTestId="quotation-pdf-title-ar"
            enAs="h3"
          />
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            data-testid="quotation-pdf-preview-close"
          >
            &times;
          </button>
        </div>
        <HtmlStackedLine
          en={`Quote No: ${quotation.quotation_number}`}
          ar={PDF_LABELS.quoteNo.ar}
        />
        <HtmlStackedLine
          en={`Valid Until: ${quotation.valid_until}`}
          ar={PDF_LABELS.validUntil.ar}
        />
        <HtmlStackedLine en={`Quote to: ${client?.name || '—'}`} ar={PDF_LABELS.quoteTo.ar} />
        {sellerTrn ? <HtmlStackedLine en={`TRN: ${sellerTrn}`} ar={PDF_LABELS.trn.ar} /> : null}
        {sellerAddress ? <p>{sellerAddress}</p> : null}
      </div>
    </div>
  );
}
