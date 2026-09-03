import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Download, Edit2, Eye, Plus } from 'lucide-react';
import toast from 'react-hot-toast';
import { getClients } from '../api/clients';
import {
  getTaxDebitNote,
  getDebitNotes,
  issueTaxDebitNote,
  type TaxDebitNoteListItem,
  type TaxDebitNoteStatus,
} from '../api/debitNotes';
import { getInvoice, getInvoices } from '../api/invoices';
import { getCurrentWorkspace } from '../api/workspaces';
import { downloadTaxDebitNotePdf } from '../components/pdf/TaxDebitNotePDF';
import { Skeleton } from '../components/Skeleton';
import { formatAed } from './quotationHelpers';
import { DebitNoteStatusBadge } from './DebitNoteStatusBadge';
import quoteStyles from './Quotations.module.css';
import styles from './DebitNotes.module.css';

const STATUSES: TaxDebitNoteStatus[] = ['DRAFT', 'ISSUED'];

export const DebitNotes = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const presetInvoiceId = searchParams.get('invoice_id') || '';
  const [status, setStatus] = useState('');
  const [clientId, setClientId] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pdfBusyId, setPdfBusyId] = useState<string | null>(null);

  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
  const { data: invoices } = useQuery({ queryKey: ['invoices'], queryFn: getInvoices });
  const { data: workspace } = useQuery({ queryKey: ['workspace'], queryFn: getCurrentWorkspace });
  const invoiceId = presetInvoiceId;
  const { data, isLoading } = useQuery({
    queryKey: ['debit-notes', { status, clientId, search, page, invoiceId }],
    queryFn: () =>
      getDebitNotes({
        page,
        per_page: 20,
        status: (status || undefined) as TaxDebitNoteStatus | undefined,
        client_id: clientId || undefined,
        invoice_id: invoiceId || undefined,
        search: search || undefined,
      }),
  });

  const issueMutation = useMutation({
    mutationFn: issueTaxDebitNote,
    onSuccess: (cn) => {
      queryClient.invalidateQueries({ queryKey: ['debit-notes'] });
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      toast.success(`${cn.debit_note_number} issued`);
    },
  });

  const downloadPdf = async (row: TaxDebitNoteListItem) => {
    setPdfBusyId(row.id);
    try {
      const cn = await getTaxDebitNote(row.id);
      const client = clients?.find((entry) => entry.id === cn.client_id);
      const invoice = await getInvoice(cn.invoice_id);
      await downloadTaxDebitNotePdf({ cn, client, workspace, invoice });
    } catch (error) {
      const axiosError = error as { response?: unknown };
      if (!axiosError.response) toast.error('Could not generate Tax Tax Debit Note PDF');
    } finally {
      setPdfBusyId(null);
    }
  };

  const rows = data?.items ?? [];
  const pagination = data?.pagination;
  const invoiceLabel = invoices?.find((row) => row.id === invoiceId)?.invoice_number;

  return (
    <div className={quoteStyles.container}>
      <div className={quoteStyles.header}>
        <h2>Debit Notes</h2>
        <button
          className={quoteStyles.primaryBtn}
          data-testid="tdn-create"
          onClick={() =>
            navigate(invoiceId ? `/debit-notes/new?invoice_id=${invoiceId}` : '/debit-notes/new')
          }
        >
          <Plus size={16} style={{ display: 'inline', marginRight: '0.5rem', verticalAlign: 'middle' }} />
          Create debit note
        </button>
      </div>

      <div className={quoteStyles.filters}>
        <div className={quoteStyles.filterGroup}>
          <label htmlFor="tdn-search">Search</label>
          <input
            id="tdn-search"
            data-testid="tdn-search"
            placeholder="CN number"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className={quoteStyles.filterGroup}>
          <label htmlFor="tdn-status-filter">Status</label>
          <select
            id="tdn-status-filter"
            data-testid="tdn-status-filter"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </div>
        <div className={quoteStyles.filterGroup}>
          <label htmlFor="tdn-client-filter">Client</label>
          <select
            id="tdn-client-filter"
            data-testid="tdn-client-filter"
            value={clientId}
            onChange={(event) => {
              setClientId(event.target.value);
              setPage(1);
            }}
          >
            <option value="">All clients</option>
            {clients?.map((client) => (
              <option key={client.id} value={client.id}>{client.name}</option>
            ))}
          </select>
        </div>
      </div>

      {invoiceId ? (
        <p className={styles.muted}>
          Showing debit notes for {invoiceLabel || 'this invoice'}.{' '}
          <button type="button" className={quoteStyles.numberLink} onClick={() => navigate('/debit-notes')}>
            Clear filter
          </button>
        </p>
      ) : null}

      <div className={quoteStyles.tableContainer}>
        {isLoading ? (
          <div style={{ padding: '2rem' }}>
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} height="40px" style={{ marginBottom: '1rem' }} />
            ))}
          </div>
        ) : (
          <table className={quoteStyles.table}>
            <thead>
              <tr>
                <th>CN #</th>
                <th>Invoice</th>
                <th>Client</th>
                <th>Status</th>
                <th>Total</th>
                <th>Issue date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const client = clients?.find((entry) => entry.id === row.client_id);
                const invoice = invoices?.find((entry) => entry.id === row.invoice_id);
                return (
                  <tr key={row.id} data-testid={`tdn-row-${row.debit_note_number}`}>
                    <td className={quoteStyles.linkCell}>
                      <button
                        type="button"
                        className={quoteStyles.tableLink}
                        data-testid={`tdn-open-${row.debit_note_number}`}
                        onClick={() => navigate(`/debit-notes/${row.id}`)}
                      >
                        {row.debit_note_number}
                      </button>
                    </td>
                    <td>{invoice?.invoice_number || '—'}</td>
                    <td>{client?.name || 'Unknown Client'}</td>
                    <td><DebitNoteStatusBadge status={row.status} /></td>
                    <td>{formatAed(row.total_amount)}</td>
                    <td>{row.issue_date}</td>
                    <td>
                      <button
                        className={quoteStyles.actionBtn}
                        title="View"
                        onClick={() => navigate(`/debit-notes/${row.id}`)}
                      >
                        <Eye size={16} />
                      </button>
                      <button
                        className={quoteStyles.actionBtn}
                        data-testid="tdn-download-pdf"
                        title="Download Tax Tax Debit Note PDF"
                        disabled={pdfBusyId === row.id}
                        onClick={() => void downloadPdf(row)}
                      >
                        <Download size={16} />
                      </button>
                      {row.status === 'DRAFT' && (
                        <>
                          <button
                            className={quoteStyles.actionBtn}
                            data-testid="tdn-edit"
                            title="Edit"
                            onClick={() => navigate(`/debit-notes/${row.id}/edit`)}
                          >
                            <Edit2 size={16} />
                          </button>
                          <button
                            className={quoteStyles.primaryBtn}
                            data-testid="tdn-issue"
                            disabled={issueMutation.isPending}
                            title="Issue (posts AR)"
                            onClick={() => issueMutation.mutate(row.id)}
                          >
                            Issue
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '2rem' }}>
                    No debit notes found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        {pagination && pagination.pages > 1 && (
          <div className={quoteStyles.pagination}>
            <button
              type="button"
              className={quoteStyles.secondaryBtn}
              disabled={!pagination.has_prev}
              onClick={() => setPage(pagination.page - 1)}
            >
              Previous
            </button>
            <span>Page {pagination.page} of {pagination.pages}</span>
            <button
              type="button"
              className={quoteStyles.secondaryBtn}
              disabled={!pagination.has_next}
              onClick={() => setPage(pagination.page + 1)}
            >
              Next
            </button>
          </div>
        )}
      </div>
      <p className={styles.muted}>
        Tax debit notes correct a tax invoice. They are not cash payments and not delivery notes.
      </p>
    </div>
  );
};
