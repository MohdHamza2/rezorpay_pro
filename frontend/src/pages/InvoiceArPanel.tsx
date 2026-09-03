import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getCreditNotes } from '../api/creditNotes';
import { getDebitNotes } from '../api/debitNotes';
import { isHttpNotFound } from '../api/errors';
import { getInvoice } from '../api/invoices';
import { isCreditableStatus } from './creditNoteHelpers';
import { InvoicePayments } from './InvoicePayments';
import { formatAed } from './quotationHelpers';
import inv from './Invoices.module.css';
import quoteStyles from './Quotations.module.css';
import styles from './CreditNotes.module.css';

type Props = {
  invoiceId: string;
  onClose: () => void;
};

export function InvoiceArPanel({ invoiceId, onClose }: Props) {
  const navigate = useNavigate();
  const { data: invoice, isLoading } = useQuery({
    queryKey: ['invoice', invoiceId],
    queryFn: () => getInvoice(invoiceId),
    retry: (count, err) => !isHttpNotFound(err) && count < 2,
  });
  const { data: notes } = useQuery({
    queryKey: ['credit-notes', { invoiceId }],
    queryFn: () => getCreditNotes({ invoice_id: invoiceId, page: 1, per_page: 100 }),
  });
  const { data: debitNotes } = useQuery({
    queryKey: ['debit-notes', { invoiceId }],
    queryFn: () => getDebitNotes({ invoice_id: invoiceId, page: 1, per_page: 100 }),
  });

  const credited = invoice?.amount_credited;
  const debited = invoice?.amount_debited;
  const showCredited = credited !== undefined && credited !== null;
  const showDebited = debited !== undefined && debited !== null && debited > 0;
  const creditable = invoice ? isCreditableStatus(invoice.status) : false;

  return (
    <div className={inv.modalOverlay} data-testid="invoice-ar-panel">
      <div className={inv.modal} style={{ maxWidth: '720px' }}>
        <div className={inv.modalHeader}>
          <h3>{invoice?.invoice_number || 'Invoice'} — amounts</h3>
          <button type="button" className={inv.closeBtn} onClick={onClose} data-testid="invoice-ar-close">&times;</button>
        </div>
        {isLoading || !invoice ? (
          <p>Loading…</p>
        ) : (
          <>
            <div className={styles.arGrid}>
              <div>
                <span className={styles.arLabel}>Invoice total</span>
                <div className={styles.arValue}>{formatAed(invoice.total_amount)}</div>
              </div>
              <div>
                <span className={styles.arLabel}>Amount paid (cash)</span>
                <div className={styles.arValue} data-testid="invoice-amount-paid">
                  {formatAed(invoice.amount_paid)}
                </div>
              </div>
              {showDebited && (
                <div>
                  <span className={styles.arLabel}>Amount debited (tax debit notes)</span>
                  <div className={styles.arValue} data-testid="invoice-amount-debited">
                    {formatAed(debited)}
                  </div>
                </div>
              )}
              {showCredited && (
                <div>
                  <span className={styles.arLabel}>Amount credited (credit notes)</span>
                  <div className={styles.arValue} data-testid="invoice-amount-credited">
                    {formatAed(credited)}
                  </div>
                </div>
              )}
              <div>
                <span className={styles.arLabel}>Balance due</span>
                <div className={styles.arValue} data-testid="invoice-balance-due">
                  {formatAed(invoice.balance_due)}
                </div>
              </div>
            </div>
            <p className={inv.hint}>
              Credit notes reduce balance due. Tax debit notes increase balance due. They are not cash payments.
            </p>
            <InvoicePayments invoiceId={invoice.id} />
            {(debitNotes?.items ?? []).length > 0 && (
              <ul>
                {(debitNotes?.items ?? []).map((row) => (
                  <li key={row.id}>
                    <button
                      type="button"
                      className={quoteStyles.numberLink}
                      onClick={() => navigate(`/debit-notes/${row.id}`)}
                    >
                      {row.tax_debit_note_number}
                    </button>
                    {' '}
                    {row.status} · {formatAed(row.total_amount)}
                  </li>
                ))}
              </ul>
            )}
            {(notes?.items ?? []).length > 0 ? (
              <ul>
                {(notes?.items ?? []).map((row) => (
                  <li key={row.id}>
                    <button
                      type="button"
                      className={quoteStyles.numberLink}
                      onClick={() => navigate(`/credit-notes/${row.id}`)}
                    >
                      {row.credit_note_number}
                    </button>
                    {' '}
                    {row.status} · {formatAed(row.total_amount)}
                  </li>
                ))}
              </ul>
            ) : (
              <p className={quoteStyles.hint}>No credit notes on this invoice yet.</p>
            )}
            <div className={inv.modalActions}>
              <button
                type="button"
                className={inv.secondaryBtn}
                onClick={() => navigate(`/debit-notes?invoice_id=${invoice.id}`)}
              >
                View debit notes
              </button>
              {creditable && (
                <button
                  type="button"
                  className={inv.primaryBtn}
                  data-testid="invoice-create-tdn"
                  onClick={() => navigate(`/debit-notes/new?invoice_id=${invoice.id}`)}
                >
                  Create debit note
                </button>
              )}
              <button
                type="button"
                className={inv.secondaryBtn}
                onClick={() => navigate(`/credit-notes?invoice_id=${invoice.id}`)}
              >
                View credit notes
              </button>
              {creditable && (
                <button
                  type="button"
                  className={inv.primaryBtn}
                  data-testid="invoice-create-cn"
                  onClick={() => navigate(`/credit-notes/new?invoice_id=${invoice.id}`)}
                >
                  Create credit note
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
