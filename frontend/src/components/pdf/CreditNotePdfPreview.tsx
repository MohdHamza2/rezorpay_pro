import type { Client } from '../../api/clients';
import type { CreditNote } from '../../api/creditNotes';
import type { Invoice } from '../../api/invoices';
import type { Workspace } from '../../api/workspaces';
import styles from '../../pages/Quotations.module.css';

function money(value: string | number | null | undefined): string {
  return Number(value ?? 0).toFixed(2);
}

function snapFirst(
  snapshot: string | null | undefined,
  live: string | null | undefined,
): string {
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
          <h3 data-testid="cn-pdf-title">Tax Credit Note</h3>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            data-testid="cn-pdf-preview-close"
          >
            &times;
          </button>
        </div>
        <p>Credit Note No: {cn.credit_note_number}</p>
        <p>Issue Date: {cn.issue_date}</p>
        <p data-testid="cn-pdf-original-invoice">Original Invoice: {originalNumber}</p>
        <p>Original Issue Date: {originalDate}</p>
        <p data-testid="cn-pdf-seller-trn">Seller TRN: {sellerTrn || '—'}</p>
        {sellerAddress ? <p>{sellerAddress}</p> : null}
        <p data-testid="cn-pdf-buyer-trn">Buyer TRN: {buyerTrn || '—'}</p>
        <p>Credit to: {snapFirst(cn.buyer_name_snapshot, client?.name) || '—'}</p>
        <p>Credit total: AED {money(cn.total_amount)}</p>
      </div>
    </div>
  );
}
