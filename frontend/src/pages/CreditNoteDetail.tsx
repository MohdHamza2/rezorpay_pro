import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { isHttpNotFound } from '../api/errors';
import { getClients } from '../api/clients';
import {
  deleteCreditNote,
  getCreditNote,
  issueCreditNote,
} from '../api/creditNotes';
import { getInvoice } from '../api/invoices';
import { getCurrentWorkspace } from '../api/workspaces';
import { downloadCreditNotePdf } from '../components/pdf/CreditNotePDF';
import { CreditNotePdfPreview } from '../components/pdf/CreditNotePdfPreview';
import { Skeleton } from '../components/Skeleton';
import { formatAed } from './quotationHelpers';
import { formatQty, REASON_LABELS } from './creditNoteHelpers';
import { CreditNoteStatusBadge } from './CreditNoteStatusBadge';
import quoteStyles from './Quotations.module.css';

export const CreditNoteDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);

  const { data: cn, isLoading, isError, error } = useQuery({
    queryKey: ['credit-note', id],
    queryFn: () => getCreditNote(id!),
    enabled: Boolean(id),
    retry: (count, err) => !isHttpNotFound(err) && count < 2,
  });
  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
  const { data: workspace } = useQuery({ queryKey: ['workspace'], queryFn: getCurrentWorkspace });
  const { data: invoice } = useQuery({
    queryKey: ['invoice', cn?.invoice_id],
    queryFn: () => getInvoice(cn!.invoice_id),
    enabled: Boolean(cn?.invoice_id),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['credit-notes'] });
    queryClient.invalidateQueries({ queryKey: ['credit-note', id] });
    queryClient.invalidateQueries({ queryKey: ['invoices'] });
    queryClient.invalidateQueries({ queryKey: ['invoice', cn?.invoice_id] });
    queryClient.invalidateQueries({ queryKey: ['clients'] });
  };

  const issueMutation = useMutation({
    mutationFn: issueCreditNote,
    onSuccess: () => {
      invalidate();
      toast.success('Credit note issued — AR posted');
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteCreditNote,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['credit-notes'] });
      toast.success('Credit note deleted');
      navigate('/credit-notes');
    },
  });

  const client = clients?.find((entry) => entry.id === cn?.client_id);
  const busy = issueMutation.isPending || deleteMutation.isPending;
  const originalNumber = cn?.original_invoice_number || invoice?.invoice_number;
  const originalDate = cn?.original_issue_date || invoice?.issue_date;

  const handleDelete = () => {
    if (!cn) return;
    if (!window.confirm('Delete this draft credit note? The CN number will not be reused.')) return;
    deleteMutation.mutate(cn.id);
  };

  const handleDownload = async () => {
    if (!cn) return;
    setPdfBusy(true);
    try {
      const fresh = await getCreditNote(cn.id);
      await downloadCreditNotePdf({ cn: fresh, client, workspace, invoice });
    } catch (err) {
      const axiosError = err as { response?: unknown };
      if (!axiosError.response) toast.error('Could not generate Tax Credit Note PDF');
    } finally {
      setPdfBusy(false);
    }
  };

  if (isError && isHttpNotFound(error)) {
    return (
      <div className={quoteStyles.container}>
        <p data-testid="cn-not-found">Credit note not found.</p>
      </div>
    );
  }

  if (isLoading || !cn) {
    return (
      <div className={quoteStyles.container}>
        {isLoading ? <Skeleton height="320px" /> : <p>Credit note not found.</p>}
      </div>
    );
  }

  return (
    <div className={quoteStyles.container} data-testid="cn-detail">
      <div className={quoteStyles.header}>
        <h2 data-testid="cn-number">{cn.credit_note_number}</h2>
        <button
          type="button"
          className={quoteStyles.secondaryBtn}
          onClick={() => navigate('/credit-notes')}
        >
          Back to list
        </button>
      </div>

      <div className={quoteStyles.pageCard}>
        <div className={quoteStyles.actions}>
          <CreditNoteStatusBadge status={cn.status} />
          <button
            type="button"
            className={quoteStyles.secondaryBtn}
            data-testid="cn-preview-pdf"
            onClick={() => setPreviewOpen(true)}
          >
            Preview PDF
          </button>
          <button
            type="button"
            className={quoteStyles.secondaryBtn}
            data-testid="cn-download-pdf"
            disabled={pdfBusy}
            onClick={() => void handleDownload()}
          >
            Download PDF
          </button>
          {cn.status === 'DRAFT' && (
            <>
              <button
                type="button"
                className={quoteStyles.secondaryBtn}
                data-testid="cn-edit"
                onClick={() => navigate(`/credit-notes/${cn.id}/edit`)}
              >
                Edit
              </button>
              <button
                type="button"
                className={quoteStyles.primaryBtn}
                data-testid="cn-issue"
                disabled={busy}
                onClick={() => issueMutation.mutate(cn.id)}
              >
                Issue
              </button>
              <button
                type="button"
                className={quoteStyles.dangerBtn}
                data-testid="cn-delete"
                disabled={busy}
                onClick={handleDelete}
              >
                Delete
              </button>
            </>
          )}
        </div>

        <div className={quoteStyles.metaGrid}>
          <div>
            <span className={quoteStyles.metaLabel}>Credit note</span>
            <div className={quoteStyles.metaValue}>{cn.credit_note_number}</div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Client</span>
            <div className={quoteStyles.metaValue}>{client?.name || 'Unknown Client'}</div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Original invoice</span>
            <div className={quoteStyles.metaValue}>{originalNumber || '—'}</div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Original issue date</span>
            <div className={quoteStyles.metaValue}>{originalDate || '—'}</div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Reason</span>
            <div className={quoteStyles.metaValue}>{REASON_LABELS[cn.reason]}</div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Issue date</span>
            <div className={quoteStyles.metaValue}>{cn.issue_date}</div>
          </div>
        </div>

        {cn.reason_notes ? (
          <p className={quoteStyles.hint}><strong>Notes:</strong> {cn.reason_notes}</p>
        ) : null}

        <div className={quoteStyles.tableContainer}>
          <table className={quoteStyles.table}>
            <thead>
              <tr>
                <th>Description</th>
                <th>SKU</th>
                <th>Qty</th>
                <th>Net</th>
                <th>VAT</th>
                <th>Gross</th>
              </tr>
            </thead>
            <tbody>
              {(cn.items ?? []).map((item) => (
                <tr key={item.id}>
                  <td>{item.description}</td>
                  <td>{item.sku_snapshot || '—'}</td>
                  <td>{formatQty(item.quantity)}</td>
                  <td>{formatAed(item.line_net)}</td>
                  <td>{formatAed(item.tax_amount)}</td>
                  <td>{formatAed(item.total_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className={quoteStyles.totals}>
          <div className={quoteStyles.totalRow}>
            <span>Subtotal</span>
            <span>{formatAed(cn.subtotal)}</span>
          </div>
          <div className={quoteStyles.totalRow}>
            <span>VAT</span>
            <span>{formatAed(cn.tax_amount)}</span>
          </div>
          <div className={quoteStyles.totalStrong}>
            <span>Credit total</span>
            <span>{formatAed(cn.total_amount)}</span>
          </div>
        </div>
      </div>

      {previewOpen && (
        <CreditNotePdfPreview
          cn={cn}
          client={client}
          workspace={workspace}
          invoice={invoice}
          onClose={() => setPreviewOpen(false)}
        />
      )}
    </div>
  );
};
