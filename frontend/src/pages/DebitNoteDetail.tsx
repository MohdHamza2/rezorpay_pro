import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { isHttpNotFound } from '../api/errors';
import { getClients } from '../api/clients';
import {
  deleteTaxDebitNote,
  getTaxDebitNote,
  issueTaxDebitNote,
} from '../api/debitNotes';
import { getInvoice } from '../api/invoices';
import { getCurrentWorkspace } from '../api/workspaces';
import { downloadTaxDebitNotePdf } from '../components/pdf/TaxDebitNotePDF';
import { TaxDebitNotePdfPreview } from '../components/pdf/TaxDebitNotePdfPreview';
import { Skeleton } from '../components/Skeleton';
import { formatAed } from './quotationHelpers';
import { formatQty, REASON_LABELS } from './debitNoteHelpers';
import { DebitNoteStatusBadge } from './DebitNoteStatusBadge';
import quoteStyles from './Quotations.module.css';

export const DebitNoteDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);

  const { data: cn, isLoading, isError, error } = useQuery({
    queryKey: ['debit-note', id],
    queryFn: () => getTaxDebitNote(id!),
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
    queryClient.invalidateQueries({ queryKey: ['debit-notes'] });
    queryClient.invalidateQueries({ queryKey: ['debit-note', id] });
    queryClient.invalidateQueries({ queryKey: ['invoices'] });
    queryClient.invalidateQueries({ queryKey: ['invoice', cn?.invoice_id] });
    queryClient.invalidateQueries({ queryKey: ['clients'] });
  };

  const issueMutation = useMutation({
    mutationFn: issueTaxDebitNote,
    onSuccess: () => {
      invalidate();
      toast.success('Debit note issued — AR posted');
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteTaxDebitNote,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['debit-notes'] });
      toast.success('Debit note deleted');
      navigate('/debit-notes');
    },
  });

  const client = clients?.find((entry) => entry.id === cn?.client_id);
  const busy = issueMutation.isPending || deleteMutation.isPending;
  const originalNumber = cn?.original_invoice_number || invoice?.invoice_number;
  const originalDate = cn?.original_issue_date || invoice?.issue_date;

  const handleDelete = () => {
    if (!cn) return;
    if (!window.confirm('Delete this draft debit note? The CN number will not be reused.')) return;
    deleteMutation.mutate(cn.id);
  };

  const handleDownload = async () => {
    if (!cn) return;
    setPdfBusy(true);
    try {
      const fresh = await getTaxDebitNote(cn.id);
      await downloadTaxDebitNotePdf({ cn: fresh, client, workspace, invoice });
    } catch (err) {
      const axiosError = err as { response?: unknown };
      if (!axiosError.response) toast.error('Could not generate Tax Tax Debit Note PDF');
    } finally {
      setPdfBusy(false);
    }
  };

  if (isError && isHttpNotFound(error)) {
    return (
      <div className={quoteStyles.container}>
        <p data-testid="tdn-not-found">Debit note not found.</p>
      </div>
    );
  }

  if (isLoading || !cn) {
    return (
      <div className={quoteStyles.container}>
        {isLoading ? <Skeleton height="320px" /> : <p>Debit note not found.</p>}
      </div>
    );
  }

  return (
    <div className={quoteStyles.container} data-testid="tdn-detail">
      <div className={quoteStyles.header}>
        <h2 data-testid="tdn-number">{cn.debit_note_number}</h2>
        <button
          type="button"
          className={quoteStyles.secondaryBtn}
          onClick={() => navigate('/debit-notes')}
        >
          Back to list
        </button>
      </div>

      <div className={quoteStyles.pageCard}>
        <div className={quoteStyles.actions}>
          <DebitNoteStatusBadge status={cn.status} />
          <button
            type="button"
            className={quoteStyles.secondaryBtn}
            data-testid="tdn-preview-pdf"
            onClick={() => setPreviewOpen(true)}
          >
            Preview PDF
          </button>
          <button
            type="button"
            className={quoteStyles.secondaryBtn}
            data-testid="tdn-download-pdf"
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
                data-testid="tdn-edit"
                onClick={() => navigate(`/debit-notes/${cn.id}/edit`)}
              >
                Edit
              </button>
              <button
                type="button"
                className={quoteStyles.primaryBtn}
                data-testid="tdn-issue"
                disabled={busy}
                onClick={() => issueMutation.mutate(cn.id)}
              >
                Issue
              </button>
              <button
                type="button"
                className={quoteStyles.dangerBtn}
                data-testid="tdn-delete"
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
            <span className={quoteStyles.metaLabel}>Debit note</span>
            <div className={quoteStyles.metaValue}>{cn.debit_note_number}</div>
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
            <span>Debit total</span>
            <span>{formatAed(cn.total_amount)}</span>
          </div>
        </div>
      </div>

      {previewOpen && (
        <TaxDebitNotePdfPreview
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
