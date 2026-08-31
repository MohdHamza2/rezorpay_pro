import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { getClients } from '../api/clients';
import {
  acceptQuotation,
  convertQuotationToInvoice,
  convertQuotationToLpo,
  deleteQuotation,
  getQuotation,
  rejectQuotation,
  sendQuotation,
} from '../api/quotations';
import { getCurrentWorkspace } from '../api/workspaces';
import { downloadQuotationPdf } from '../components/pdf/QuotationPDF';
import { QuotationPdfPreview } from '../components/pdf/QuotationPdfPreview';
import { Skeleton } from '../components/Skeleton';
import { formatAed } from './quotationHelpers';
import { QuotationStatusBadge } from './QuotationStatusBadge';
import styles from './Quotations.module.css';

export const QuotationDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);

  const { data: quote, isLoading } = useQuery({
    queryKey: ['quotation', id],
    queryFn: () => getQuotation(id!),
    enabled: Boolean(id),
  });
  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
  const { data: workspace } = useQuery({ queryKey: ['workspace'], queryFn: getCurrentWorkspace });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['quotations'] });
    queryClient.invalidateQueries({ queryKey: ['quotation', id] });
  };

  const sendMutation = useMutation({
    mutationFn: sendQuotation,
    onSuccess: () => {
      invalidate();
      toast.success('Quotation sent');
    },
  });
  const acceptMutation = useMutation({
    mutationFn: acceptQuotation,
    onSuccess: () => {
      invalidate();
      toast.success('Quotation accepted');
    },
  });
  const rejectMutation = useMutation({
    mutationFn: ({ quoteId, reason }: { quoteId: string; reason?: string }) =>
      rejectQuotation(quoteId, reason),
    onSuccess: () => {
      invalidate();
      toast.success('Quotation rejected');
    },
  });
  const convertMutation = useMutation({
    mutationFn: convertQuotationToInvoice,
    onSuccess: (invoice) => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      toast.success(`Converted to ${invoice.invoice_number} (DRAFT)`);
      navigate('/invoices');
    },
  });
  const convertLpoMutation = useMutation({
    mutationFn: (quoteId: string) => convertQuotationToLpo(quoteId),
    onSuccess: (lpo) => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ['lpos'] });
      toast.success(`Converted to ${lpo.lpo_number} (DRAFT)`);
      navigate(`/lpos/${lpo.id}`);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteQuotation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quotations'] });
      toast.success('Quotation deleted');
      navigate('/quotations');
    },
  });

  const client = clients?.find((entry) => entry.id === quote?.client_id);
  const busy =
    sendMutation.isPending ||
    acceptMutation.isPending ||
    rejectMutation.isPending ||
    convertMutation.isPending ||
    convertLpoMutation.isPending ||
    deleteMutation.isPending;

  const handleReject = () => {
    if (!quote) return;
    const reason = window.prompt('Rejection reason (optional)');
    if (reason === null) return;
    rejectMutation.mutate({ quoteId: quote.id, reason: reason.trim() || undefined });
  };

  const handleDelete = () => {
    if (!quote) return;
    if (!window.confirm('Delete this draft quotation?')) return;
    deleteMutation.mutate(quote.id);
  };

  const handleDownload = async () => {
    if (!quote) return;
    setPdfBusy(true);
    try {
      const fresh = await getQuotation(quote.id);
      await downloadQuotationPdf({ quotation: fresh, client, workspace });
    } catch (error) {
      const axiosError = error as { response?: unknown };
      if (!axiosError.response) toast.error('Could not generate quotation PDF');
    } finally {
      setPdfBusy(false);
    }
  };

  if (isLoading || !quote) {
    return (
      <div className={styles.container}>
        {isLoading ? <Skeleton height="320px" /> : <p>Quotation not found.</p>}
      </div>
    );
  }

  return (
    <div className={styles.container} data-testid="quotation-detail">
      <div className={styles.header}>
        <h2 data-testid="quotation-number">{quote.quotation_number}</h2>
        <button type="button" className={styles.secondaryBtn} onClick={() => navigate('/quotations')}>
          Back to list
        </button>
      </div>

      <div className={styles.pageCard}>
        <div className={styles.actions}>
          <QuotationStatusBadge status={quote.status} />
          <button
            type="button"
            className={styles.secondaryBtn}
            data-testid="quotation-preview-pdf"
            onClick={() => setPreviewOpen(true)}
          >
            Preview PDF
          </button>
          <button
            type="button"
            className={styles.secondaryBtn}
            data-testid="quotation-download-pdf"
            disabled={pdfBusy}
            onClick={() => void handleDownload()}
          >
            Download PDF
          </button>
          {quote.status === 'DRAFT' && (
            <>
              <button
                type="button"
                className={styles.secondaryBtn}
                data-testid="quotation-edit"
                onClick={() => navigate(`/quotations/${quote.id}/edit`)}
              >
                Edit
              </button>
              <button
                type="button"
                className={styles.primaryBtn}
                data-testid="quotation-send"
                disabled={busy}
                onClick={() => sendMutation.mutate(quote.id)}
              >
                Send
              </button>
              <button
                type="button"
                className={styles.dangerBtn}
                data-testid="quotation-delete"
                disabled={busy}
                onClick={handleDelete}
              >
                Delete
              </button>
            </>
          )}
          {quote.status === 'SENT' && (
            <>
              <button
                type="button"
                className={styles.primaryBtn}
                data-testid="quotation-accept"
                disabled={busy}
                onClick={() => acceptMutation.mutate(quote.id)}
              >
                Accept
              </button>
              <button
                type="button"
                className={styles.dangerBtn}
                data-testid="quotation-reject"
                disabled={busy}
                onClick={handleReject}
              >
                Reject
              </button>
              <p className={styles.hint} style={{ margin: 0, alignSelf: 'center' }}>
                Accept first, then convert to a draft invoice.
              </p>
            </>
          )}
          {quote.status === 'ACCEPTED' && (
            <>
              <button
                type="button"
                className={styles.primaryBtn}
                data-testid="quotation-convert"
                disabled={busy || Boolean(quote.converted_lpo_id)}
                onClick={() => convertMutation.mutate(quote.id)}
              >
                Convert to invoice
              </button>
              <button
                type="button"
                className={styles.secondaryBtn}
                data-testid="quotation-convert-lpo"
                disabled={busy || Boolean(quote.converted_invoice_id)}
                onClick={() => convertLpoMutation.mutate(quote.id)}
              >
                Convert to LPO
              </button>
            </>
          )}
          {quote.status === 'CONVERTED' && quote.converted_invoice_id && (
            <button type="button" className={styles.primaryBtn} onClick={() => navigate('/invoices')}>
              Open draft invoice
            </button>
          )}
          {quote.status === 'CONVERTED' && quote.converted_lpo_id && (
            <button
              type="button"
              className={styles.primaryBtn}
              data-testid="quotation-open-lpo"
              onClick={() => navigate(`/lpos/${quote.converted_lpo_id}`)}
            >
              Open LPO
            </button>
          )}
        </div>

        <div className={styles.metaGrid}>
          <div>
            <span className={styles.metaLabel}>Client</span>
            <div className={styles.metaValue}>{client?.name || 'Unknown Client'}</div>
          </div>
          <div>
            <span className={styles.metaLabel}>Currency</span>
            <div className={styles.metaValue}>AED</div>
          </div>
          <div>
            <span className={styles.metaLabel}>Quotation date</span>
            <div className={styles.metaValue}>{quote.quotation_date}</div>
          </div>
          <div>
            <span className={styles.metaLabel}>Valid until</span>
            <div className={styles.metaValue}>{quote.valid_until}</div>
          </div>
        </div>

        {quote.notes ? (
          <p className={styles.hint}><strong>Notes:</strong> {quote.notes}</p>
        ) : null}
        {quote.rejection_reason ? (
          <p className={styles.hint}><strong>Rejection reason:</strong> {quote.rejection_reason}</p>
        ) : null}

        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Description</th>
                <th>Qty</th>
                <th>Unit</th>
                <th>Net</th>
                <th>VAT%</th>
                <th>VAT</th>
                <th>Gross</th>
              </tr>
            </thead>
            <tbody>
              {(quote.items ?? []).map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.description}
                    {item.sku_snapshot ? <div className={styles.hint}>SKU: {item.sku_snapshot}</div> : null}
                  </td>
                  <td>{item.quantity}</td>
                  <td>{formatAed(item.unit_price)}</td>
                  <td>{formatAed(item.line_net)}</td>
                  <td>{Number(item.tax_rate ?? 0).toFixed(2)}%</td>
                  <td>{formatAed(item.tax_amount)}</td>
                  <td>{formatAed(item.total_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className={styles.totals}>
          <div className={styles.totalRow}>
            <span>Subtotal (excl. VAT)</span>
            <span>{formatAed(quote.subtotal)}</span>
          </div>
          <div className={styles.totalRow}>
            <span>VAT</span>
            <span>{formatAed(quote.tax_amount)}</span>
          </div>
          <div className={styles.totalStrong}>
            <span>Total</span>
            <span>{formatAed(quote.total_amount)}</span>
          </div>
        </div>
      </div>

      {previewOpen && (
        <QuotationPdfPreview
          quotation={quote}
          client={client}
          workspace={workspace}
          onClose={() => setPreviewOpen(false)}
        />
      )}
    </div>
  );
};
