import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Download, Edit2, Eye, Plus } from 'lucide-react';
import toast from 'react-hot-toast';
import { extractApiError } from '../api/errors';
import { getClients } from '../api/clients';
import { getLpo, getLpos, receiveLpo, type LpoListItem, type LpoStatus } from '../api/lpos';
import { getQuotation } from '../api/quotations';
import { getCurrentWorkspace } from '../api/workspaces';
import { downloadLpoPdf } from '../components/pdf/LpoPDF';
import { Skeleton } from '../components/Skeleton';
import { formatAed } from './quotationHelpers';
import { LpoStatusBadge } from './LpoStatusBadge';
import quoteStyles from './Quotations.module.css';
import styles from './Lpos.module.css';
import inv from './Invoices.module.css';

const STATUSES: LpoStatus[] = ['DRAFT', 'RECEIVED', 'PARTIAL', 'INVOICED', 'CANCELLED'];

export const Lpos = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState('');
  const [clientId, setClientId] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pdfBusyId, setPdfBusyId] = useState<string | null>(null);
  const [creditHoldMessage, setCreditHoldMessage] = useState<string | null>(null);

  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
  const { data: workspace } = useQuery({ queryKey: ['workspace'], queryFn: getCurrentWorkspace });
  const { data, isLoading } = useQuery({
    queryKey: ['lpos', { status, clientId, search, page }],
    queryFn: () =>
      getLpos({
        page,
        per_page: 20,
        status: (status || undefined) as LpoStatus | undefined,
        client_id: clientId || undefined,
        search: search || undefined,
      }),
  });

  const receiveMutation = useMutation({
    mutationFn: receiveLpo,
    onSuccess: (lpo) => {
      queryClient.invalidateQueries({ queryKey: ['lpos'] });
      setCreditHoldMessage(null);
      toast.success(`${lpo.lpo_number} received`);
    },
    onError: (error: unknown) => {
      const parsed = extractApiError(error);
      if (parsed.code === 'CREDIT_HOLD') {
        setCreditHoldMessage(parsed.message);
        toast.error(parsed.message);
      }
    },
  });

  const downloadPdf = async (row: LpoListItem) => {
    setPdfBusyId(row.id);
    try {
      const lpo = await getLpo(row.id);
      const client = clients?.find((entry) => entry.id === lpo.client_id);
      let quotationNumber: string | undefined;
      if (lpo.quotation_id) {
        try {
          const quote = await getQuotation(lpo.quotation_id);
          quotationNumber = quote.quotation_number;
        } catch {
          quotationNumber = undefined;
        }
      }
      await downloadLpoPdf({ lpo, client, workspace, quotationNumber });
    } catch (error) {
      const axiosError = error as { response?: unknown };
      if (!axiosError.response) toast.error('Could not generate LPO PDF');
    } finally {
      setPdfBusyId(null);
    }
  };

  const rows = data?.items ?? [];
  const pagination = data?.pagination;

  return (
    <div className={quoteStyles.container}>
      <div className={quoteStyles.header}>
        <h2>Customer LPOs</h2>
        <button
          className={quoteStyles.primaryBtn}
          data-testid="lpo-create"
          onClick={() => navigate('/lpos/new')}
        >
          <Plus size={16} style={{ display: 'inline', marginRight: '0.5rem', verticalAlign: 'middle' }} />
          Create LPO
        </button>
      </div>

      {creditHoldMessage && (
        <div className={inv.ftaBanner} data-testid="credit-hold" role="alert">
          {creditHoldMessage}
        </div>
      )}

      <div className={quoteStyles.filters}>
        <div className={quoteStyles.filterGroup}>
          <label htmlFor="lpo-search">Search</label>
          <input
            id="lpo-search"
            data-testid="lpo-search"
            placeholder="LPO or customer PO number"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className={quoteStyles.filterGroup}>
          <label htmlFor="lpo-status-filter">Status</label>
          <select
            id="lpo-status-filter"
            data-testid="lpo-status-filter"
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
          <label htmlFor="lpo-client-filter">Client</label>
          <select
            id="lpo-client-filter"
            data-testid="lpo-client-filter"
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
                <th>LPO #</th>
                <th>Customer PO</th>
                <th>Client</th>
                <th>Status</th>
                <th>Total</th>
                <th>Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const client = clients?.find((entry) => entry.id === row.client_id);
                return (
                  <tr key={row.id} data-testid={`lpo-row-${row.lpo_number}`}>
                    <td>
                      <button
                        type="button"
                        className={quoteStyles.numberLink}
                        data-testid={`lpo-open-${row.lpo_number}`}
                        onClick={() => navigate(`/lpos/${row.id}`)}
                      >
                        {row.lpo_number}
                      </button>
                    </td>
                    <td>
                      <span data-testid="lpo-customer-po">{row.customer_po_number || '—'}</span>
                    </td>
                    <td>{client?.name || 'Unknown Client'}</td>
                    <td><LpoStatusBadge status={row.status} /></td>
                    <td>{formatAed(row.total_amount)}</td>
                    <td>{row.lpo_date}</td>
                    <td>
                      <button
                        className={quoteStyles.actionBtn}
                        title="View"
                        onClick={() => navigate(`/lpos/${row.id}`)}
                      >
                        <Eye size={16} />
                      </button>
                      <button
                        className={quoteStyles.actionBtn}
                        data-testid="lpo-download-pdf"
                        title="Download LPO PDF"
                        disabled={pdfBusyId === row.id}
                        onClick={() => void downloadPdf(row)}
                      >
                        <Download size={16} />
                      </button>
                      {row.status === 'DRAFT' && (
                        <>
                          <button
                            className={quoteStyles.actionBtn}
                            data-testid="lpo-edit"
                            title="Edit"
                            onClick={() => navigate(`/lpos/${row.id}/edit`)}
                          >
                            <Edit2 size={16} />
                          </button>
                          <button
                            className={quoteStyles.primaryBtn}
                            data-testid="lpo-receive"
                            disabled={receiveMutation.isPending}
                            title={
                              client?.credit_status === 'HOLD' && workspace?.block_po_on_hold
                                ? 'Blocked while this client is on credit HOLD'
                                : 'Receive'
                            }
                            onClick={() => receiveMutation.mutate(row.id)}
                          >
                            Receive
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
                    No customer LPOs found.
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
        Customer LPOs are inbound demand. Supplier purchase orders stay under Purchasing.
      </p>
    </div>
  );
};
