import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Download, Edit2, Eye, Plus, Send } from 'lucide-react';
import toast from 'react-hot-toast';
import { getClients } from '../api/clients';
import {
  convertQuotationToInvoice,
  convertQuotationToLpo,
  getQuotation,
  getQuotations,
  sendQuotation,
  type QuotationListItem,
  type QuotationStatus,
} from '../api/quotations';
import { getCurrentWorkspace } from '../api/workspaces';
import { downloadQuotationPdf } from '../components/pdf/QuotationPDF';
import { Skeleton } from '../components/Skeleton';
import { formatAed } from './quotationHelpers';
import { QuotationStatusBadge } from './QuotationStatusBadge';
import styles from './Quotations.module.css';

const STATUSES: QuotationStatus[] = [
  'DRAFT',
  'SENT',
  'ACCEPTED',
  'REJECTED',
  'EXPIRED',
  'CONVERTED',
];

export const Quotations = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState('');
  const [clientId, setClientId] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pdfBusyId, setPdfBusyId] = useState<string | null>(null);

  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
  const { data: workspace } = useQuery({ queryKey: ['workspace'], queryFn: getCurrentWorkspace });
  const { data, isLoading } = useQuery({
    queryKey: ['quotations', { status, clientId, search, page }],
    queryFn: () =>
      getQuotations({
        page,
        per_page: 20,
        status: (status || undefined) as QuotationStatus | undefined,
        client_id: clientId || undefined,
        search: search || undefined,
      }),
  });

  const sendMutation = useMutation({
    mutationFn: sendQuotation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quotations'] });
      toast.success('Quotation sent');
    },
  });

  const convertMutation = useMutation({
    mutationFn: convertQuotationToInvoice,
    onSuccess: (invoice) => {
      queryClient.invalidateQueries({ queryKey: ['quotations'] });
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      toast.success(`Converted to ${invoice.invoice_number} (DRAFT)`);
      navigate('/invoices');
    },
  });

  const convertLpoMutation = useMutation({
    mutationFn: (quoteId: string) => convertQuotationToLpo(quoteId),
    onSuccess: (lpo) => {
      queryClient.invalidateQueries({ queryKey: ['quotations'] });
      queryClient.invalidateQueries({ queryKey: ['lpos'] });
      toast.success(`Converted to ${lpo.lpo_number} (DRAFT)`);
      navigate(`/lpos/${lpo.id}`);
    },
  });

  const downloadPdf = async (row: QuotationListItem) => {
    setPdfBusyId(row.id);
    try {
      const quotation = await getQuotation(row.id);
      const client = clients?.find((entry) => entry.id === quotation.client_id);
      await downloadQuotationPdf({ quotation, client, workspace });
    } catch (error) {
      const axiosError = error as { response?: unknown };
      if (!axiosError.response) toast.error('Could not generate quotation PDF');
    } finally {
      setPdfBusyId(null);
    }
  };

  const quotes = data?.items ?? [];
  const pagination = data?.pagination;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Quotations</h2>
        <button
          className={styles.primaryBtn}
          data-testid="quotation-create"
          onClick={() => navigate('/quotations/new')}
        >
          <Plus size={16} style={{ display: 'inline', marginRight: '0.5rem', verticalAlign: 'middle' }} />
          Create Quotation
        </button>
      </div>

      <div className={styles.filters}>
        <div className={styles.filterGroup}>
          <label htmlFor="quotation-search">Search</label>
          <input
            id="quotation-search"
            data-testid="quotation-search"
            placeholder="Quote number"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className={styles.filterGroup}>
          <label htmlFor="quotation-status-filter">Status</label>
          <select
            id="quotation-status-filter"
            data-testid="quotation-status-filter"
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
        <div className={styles.filterGroup}>
          <label htmlFor="quotation-client-filter">Client</label>
          <select
            id="quotation-client-filter"
            data-testid="quotation-client-filter"
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

      <div className={styles.tableContainer}>
        {isLoading ? (
          <div style={{ padding: '2rem' }}>
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} height="40px" style={{ marginBottom: '1rem' }} />
            ))}
          </div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Quote #</th>
                <th>Client</th>
                <th>Status</th>
                <th>Total</th>
                <th>Date</th>
                <th>Valid until</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {quotes.map((row) => {
                const client = clients?.find((entry) => entry.id === row.client_id);
                return (
                  <tr key={row.id} data-testid={`quotation-row-${row.quotation_number}`}>
                    <td>
                      <button
                        type="button"
                        className={styles.numberLink}
                        data-testid={`quotation-open-${row.quotation_number}`}
                        onClick={() => navigate(`/quotations/${row.id}`)}
                      >
                        {row.quotation_number}
                      </button>
                    </td>
                    <td>{client?.name || 'Unknown Client'}</td>
                    <td><QuotationStatusBadge status={row.status} /></td>
                    <td>{formatAed(row.total_amount)}</td>
                    <td>{row.quotation_date}</td>
                    <td>{row.valid_until}</td>
                    <td>
                      <button
                        className={styles.actionBtn}
                        title="View"
                        onClick={() => navigate(`/quotations/${row.id}`)}
                      >
                        <Eye size={16} />
                      </button>
                      <button
                        className={styles.actionBtn}
                        data-testid="quotation-download-pdf"
                        title="Download quotation PDF"
                        disabled={pdfBusyId === row.id}
                        onClick={() => void downloadPdf(row)}
                      >
                        <Download size={16} />
                      </button>
                      {row.status === 'DRAFT' && (
                        <>
                          <button
                            className={styles.actionBtn}
                            data-testid="quotation-edit"
                            title="Edit"
                            onClick={() => navigate(`/quotations/${row.id}/edit`)}
                          >
                            <Edit2 size={16} />
                          </button>
                          <button
                            className={styles.actionBtn}
                            data-testid="quotation-send"
                            title="Send"
                            onClick={() => sendMutation.mutate(row.id)}
                          >
                            <Send size={16} />
                          </button>
                        </>
                      )}
                      {row.status === 'ACCEPTED' && (
                        <>
                          <button
                            className={styles.primaryBtn}
                            data-testid="quotation-convert"
                            disabled={convertMutation.isPending || Boolean(row.converted_lpo_id)}
                            onClick={() => convertMutation.mutate(row.id)}
                          >
                            Convert
                          </button>
                          <button
                            className={styles.secondaryBtn}
                            data-testid="quotation-convert-lpo"
                            disabled={convertLpoMutation.isPending || Boolean(row.converted_invoice_id)}
                            onClick={() => convertLpoMutation.mutate(row.id)}
                          >
                            Convert to LPO
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
              {quotes.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '2rem' }}>
                    No quotations found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        {pagination && pagination.pages > 1 && (
          <div className={styles.pagination}>
            <button
              type="button"
              className={styles.secondaryBtn}
              disabled={!pagination.has_prev}
              onClick={() => setPage(pagination.page - 1)}
            >
              Previous
            </button>
            <span>Page {pagination.page} of {pagination.pages}</span>
            <button
              type="button"
              className={styles.secondaryBtn}
              disabled={!pagination.has_next}
              onClick={() => setPage(pagination.page + 1)}
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
