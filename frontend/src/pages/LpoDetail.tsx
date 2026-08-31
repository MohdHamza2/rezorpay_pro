import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { extractApiError } from '../api/errors';
import { getClients } from '../api/clients';
import {
  cancelLpo,
  createLpoInvoice,
  deleteLpo,
  getLpo,
  receiveLpo,
  type LpoInvoiceCreatePayload,
  type LpoInvoiceLineWrite,
  type LpoItem,
} from '../api/lpos';
import { getQuotation } from '../api/quotations';
import { getCurrentWorkspace } from '../api/workspaces';
import { downloadLpoPdf } from '../components/pdf/LpoPDF';
import { LpoPdfPreview } from '../components/pdf/LpoPdfPreview';
import { Skeleton } from '../components/Skeleton';
import { remainingQty } from './lpoHelpers';
import { formatAed, parseAmount } from './quotationHelpers';
import { LpoStatusBadge } from './LpoStatusBadge';
import quoteStyles from './Quotations.module.css';
import styles from './Lpos.module.css';
import inv from './Invoices.module.css';

function qtyMapFromItems(items: LpoItem[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const item of items) {
    const remaining = remainingQty(item);
    map[item.id] = remaining > 0 ? String(remaining) : '0';
  }
  return map;
}

function buildInvoiceItems(
  items: LpoItem[],
  qtyMap: Record<string, string>,
): LpoInvoiceLineWrite[] {
  const selected: LpoInvoiceLineWrite[] = [];
  for (const item of items) {
    const qty = parseAmount(qtyMap[item.id]);
    if (qty === undefined || qty <= 0) continue;
    selected.push({ customer_purchase_order_item_id: item.id, quantity: qty });
  }
  return selected;
}

function validateInvoiceQtys(
  items: LpoItem[],
  qtyMap: Record<string, string>,
): string | null {
  for (const item of items) {
    const raw = qtyMap[item.id];
    if (raw == null || raw.trim() === '' || raw === '0') continue;
    const qty = parseAmount(raw);
    const remaining = remainingQty(item);
    if (qty === undefined || qty <= 0) return 'Invoice qty must be greater than 0';
    if (qty > remaining) return `Cannot invoice more than remaining (${remaining})`;
  }
  return null;
}

export const LpoDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [qtyMap, setQtyMap] = useState<Record<string, string>>({});
  const [invoiceNotes, setInvoiceNotes] = useState('');
  const [creditHoldMessage, setCreditHoldMessage] = useState<string | null>(null);

  const { data: lpo, isLoading } = useQuery({
    queryKey: ['lpo', id],
    queryFn: () => getLpo(id!),
    enabled: Boolean(id),
  });
  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
  const { data: workspace } = useQuery({ queryKey: ['workspace'], queryFn: getCurrentWorkspace });
  const { data: linkedQuote } = useQuery({
    queryKey: ['quotation', lpo?.quotation_id],
    queryFn: () => getQuotation(lpo!.quotation_id!),
    enabled: Boolean(lpo?.quotation_id),
  });

  useEffect(() => {
    if (lpo?.items) setQtyMap(qtyMapFromItems(lpo.items));
  }, [lpo]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['lpos'] });
    queryClient.invalidateQueries({ queryKey: ['lpo', id] });
  };

  const receiveMutation = useMutation({
    mutationFn: receiveLpo,
    onSuccess: () => {
      invalidate();
      setCreditHoldMessage(null);
      toast.success('LPO received');
    },
    onError: (error: unknown) => {
      const parsed = extractApiError(error);
      if (parsed.code === 'CREDIT_HOLD') {
        setCreditHoldMessage(parsed.message);
        toast.error(parsed.message);
      }
    },
  });
  const cancelMutation = useMutation({
    mutationFn: ({ lpoId, reason }: { lpoId: string; reason?: string }) =>
      cancelLpo(lpoId, reason),
    onSuccess: () => {
      invalidate();
      toast.success('LPO cancelled');
    },
  });
  const invoiceMutation = useMutation({
    mutationFn: ({ lpoId, data }: { lpoId: string; data: LpoInvoiceCreatePayload }) =>
      createLpoInvoice(lpoId, data),
    onSuccess: (invoice) => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      toast.success(`Created ${invoice.invoice_number} (DRAFT)`);
      navigate('/invoices');
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteLpo,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lpos'] });
      toast.success('LPO deleted');
      navigate('/lpos');
    },
  });

  const client = clients?.find((entry) => entry.id === lpo?.client_id);
  const busy =
    receiveMutation.isPending ||
    cancelMutation.isPending ||
    invoiceMutation.isPending ||
    deleteMutation.isPending;
  const canInvoice = lpo?.status === 'RECEIVED' || lpo?.status === 'PARTIAL';

  const handleCancel = () => {
    if (!lpo) return;
    const reason = window.prompt('Cancellation reason (optional)');
    if (reason === null) return;
    cancelMutation.mutate({ lpoId: lpo.id, reason: reason.trim() || undefined });
  };

  const handleDelete = () => {
    if (!lpo) return;
    if (!window.confirm('Delete this draft LPO?')) return;
    deleteMutation.mutate(lpo.id);
  };

  const handleInvoice = () => {
    if (!lpo) return;
    const error = validateInvoiceQtys(lpo.items ?? [], qtyMap);
    if (error) {
      toast.error(error);
      return;
    }
    const items = buildInvoiceItems(lpo.items ?? [], qtyMap);
    if (items.length === 0) {
      toast.error('Enter remaining quantity on at least one line');
      return;
    }
    const notes = invoiceNotes.trim();
    invoiceMutation.mutate({
      lpoId: lpo.id,
      data: notes ? { items, notes } : { items },
    });
  };

  const handleDownload = async () => {
    if (!lpo) return;
    setPdfBusy(true);
    try {
      const fresh = await getLpo(lpo.id);
      await downloadLpoPdf({
        lpo: fresh,
        client,
        workspace,
        quotationNumber: linkedQuote?.quotation_number,
      });
    } catch (error) {
      const axiosError = error as { response?: unknown };
      if (!axiosError.response) toast.error('Could not generate LPO PDF');
    } finally {
      setPdfBusy(false);
    }
  };

  if (isLoading || !lpo) {
    return (
      <div className={quoteStyles.container}>
        {isLoading ? <Skeleton height="320px" /> : <p>LPO not found.</p>}
      </div>
    );
  }

  return (
    <div className={quoteStyles.container} data-testid="lpo-detail">
      <div className={quoteStyles.header}>
        <h2 data-testid="lpo-number">{lpo.lpo_number}</h2>
        <button type="button" className={quoteStyles.secondaryBtn} onClick={() => navigate('/lpos')}>
          Back to list
        </button>
      </div>

      <div className={quoteStyles.pageCard}>
        {creditHoldMessage && (
          <div className={inv.ftaBanner} data-testid="credit-hold" role="alert">
            {creditHoldMessage}
          </div>
        )}
        <div className={quoteStyles.actions}>
          <LpoStatusBadge status={lpo.status} />
          <button
            type="button"
            className={quoteStyles.secondaryBtn}
            data-testid="lpo-preview-pdf"
            onClick={() => setPreviewOpen(true)}
          >
            Preview PDF
          </button>
          <button
            type="button"
            className={quoteStyles.secondaryBtn}
            data-testid="lpo-download-pdf"
            disabled={pdfBusy}
            onClick={() => void handleDownload()}
          >
            Download PDF
          </button>
          {lpo.status === 'DRAFT' && (
            <>
              <button
                type="button"
                className={quoteStyles.secondaryBtn}
                data-testid="lpo-edit"
                onClick={() => navigate(`/lpos/${lpo.id}/edit`)}
              >
                Edit
              </button>
              <button
                type="button"
                className={quoteStyles.primaryBtn}
                data-testid="lpo-receive"
                disabled={busy}
                title={
                  client?.credit_status === 'HOLD' && workspace?.block_po_on_hold
                    ? 'Blocked while this client is on credit HOLD'
                    : 'Receive'
                }
                onClick={() => receiveMutation.mutate(lpo.id)}
              >
                Receive
              </button>
              <button
                type="button"
                className={quoteStyles.dangerBtn}
                data-testid="lpo-delete"
                disabled={busy}
                onClick={handleDelete}
              >
                Delete
              </button>
            </>
          )}
          {lpo.status === 'RECEIVED' && (
            <button
              type="button"
              className={quoteStyles.dangerBtn}
              data-testid="lpo-cancel"
              disabled={busy}
              onClick={handleCancel}
            >
              Cancel LPO
            </button>
          )}
        </div>

        <div className={quoteStyles.metaGrid}>
          <div>
            <span className={quoteStyles.metaLabel}>Internal number</span>
            <div className={quoteStyles.metaValue}>{lpo.lpo_number}</div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Customer PO</span>
            <div className={quoteStyles.metaValue} data-testid="lpo-customer-po">
              {lpo.customer_po_number || '—'}
            </div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Client</span>
            <div className={quoteStyles.metaValue}>{client?.name || 'Unknown Client'}</div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Currency</span>
            <div className={quoteStyles.metaValue}>AED</div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>LPO date</span>
            <div className={quoteStyles.metaValue}>{lpo.lpo_date}</div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Expected delivery</span>
            <div className={quoteStyles.metaValue}>{lpo.expected_delivery_date || '—'}</div>
          </div>
          {linkedQuote ? (
            <div>
              <span className={quoteStyles.metaLabel}>Quote</span>
              <div className={quoteStyles.metaValue}>{linkedQuote.quotation_number}</div>
            </div>
          ) : null}
        </div>

        {lpo.notes ? (
          <p className={quoteStyles.hint}><strong>Notes:</strong> {lpo.notes}</p>
        ) : null}
        {lpo.cancellation_reason ? (
          <p className={quoteStyles.hint}><strong>Cancellation reason:</strong> {lpo.cancellation_reason}</p>
        ) : null}

        <div className={quoteStyles.tableContainer}>
          <table className={quoteStyles.table}>
            <thead>
              <tr>
                <th>Description</th>
                <th>Ordered</th>
                <th>Invoiced</th>
                <th>Remaining</th>
                <th>Unit</th>
                <th>Net</th>
                <th>VAT%</th>
                <th>Gross</th>
              </tr>
            </thead>
            <tbody>
              {(lpo.items ?? []).map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.description}
                    {item.sku_snapshot ? <div className={quoteStyles.hint}>SKU: {item.sku_snapshot}</div> : null}
                  </td>
                  <td>{item.quantity}</td>
                  <td>{item.quantity_invoiced}</td>
                  <td>{item.quantity_remaining}</td>
                  <td>{formatAed(item.unit_price)}</td>
                  <td>{formatAed(item.line_net)}</td>
                  <td>{Number(item.tax_rate ?? 0).toFixed(2)}%</td>
                  <td>{formatAed(item.total_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className={quoteStyles.totals}>
          <div className={quoteStyles.totalRow}>
            <span>Subtotal (excl. VAT)</span>
            <span>{formatAed(lpo.subtotal)}</span>
          </div>
          <div className={quoteStyles.totalRow}>
            <span>VAT</span>
            <span>{formatAed(lpo.tax_amount)}</span>
          </div>
          <div className={quoteStyles.totalStrong}>
            <span>Total (ordered)</span>
            <span>{formatAed(lpo.total_amount)}</span>
          </div>
        </div>

        {(lpo.invoices ?? []).length > 0 && (
          <div className={styles.invoicePanel}>
            <h4>Linked invoices</h4>
            <div className={quoteStyles.tableContainer}>
              <table className={quoteStyles.table}>
                <thead>
                  <tr>
                    <th>Invoice #</th>
                    <th>Status</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {lpo.invoices?.map((invoice) => (
                    <tr key={invoice.id}>
                      <td>{invoice.invoice_number}</td>
                      <td>{invoice.status}</td>
                      <td>{formatAed(invoice.total_amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {canInvoice && (
          <div className={styles.invoicePanel} data-testid="lpo-invoice-panel">
            <h4>Invoice remaining</h4>
            <p className={quoteStyles.hint}>
              Enter qty per line (cannot exceed remaining). Creates a DRAFT tax invoice — not this LPO.
            </p>
            <div className={quoteStyles.tableContainer}>
              <table className={quoteStyles.table}>
                <thead>
                  <tr>
                    <th>Description</th>
                    <th>Remaining</th>
                    <th>Qty to invoice</th>
                  </tr>
                </thead>
                <tbody>
                  {(lpo.items ?? []).map((item, index) => {
                    const remaining = remainingQty(item);
                    return (
                      <tr key={item.id}>
                        <td>{item.description}</td>
                        <td data-testid={`lpo-remaining-${index}`}>{remaining}</td>
                        <td>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            max={remaining}
                            className={styles.qtyInput}
                            data-testid={`lpo-invoice-qty-${index}`}
                            disabled={remaining <= 0}
                            value={qtyMap[item.id] ?? '0'}
                            onChange={(event) =>
                              setQtyMap((current) => ({
                                ...current,
                                [item.id]: event.target.value,
                              }))
                            }
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className={inv.formGroup} style={{ marginTop: '1rem' }}>
              <label htmlFor="lpo-invoice-notes">Invoice notes (optional)</label>
              <textarea
                id="lpo-invoice-notes"
                rows={2}
                data-testid="lpo-invoice-notes"
                value={invoiceNotes}
                onChange={(event) => setInvoiceNotes(event.target.value)}
              />
            </div>
            <button
              type="button"
              className={quoteStyles.primaryBtn}
              data-testid="lpo-invoice"
              disabled={busy}
              onClick={handleInvoice}
            >
              Create draft invoice
            </button>
          </div>
        )}
      </div>

      {previewOpen && (
        <LpoPdfPreview
          lpo={lpo}
          client={client}
          workspace={workspace}
          quotationNumber={linkedQuote?.quotation_number}
          onClose={() => setPreviewOpen(false)}
        />
      )}
    </div>
  );
};
