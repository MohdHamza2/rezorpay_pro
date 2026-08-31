import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Download, Edit2, Eye, Plus } from 'lucide-react';
import toast from 'react-hot-toast';
import { extractApiError } from '../api/errors';
import { getClients } from '../api/clients';
import {
  confirmDeliveryNote,
  getDeliveryNote,
  getDeliveryNotes,
  type DeliveryNoteListItem,
  type DeliveryNoteStatus,
} from '../api/deliveryNotes';
import { getInvoice } from '../api/invoices';
import { getLpo } from '../api/lpos';
import { getCurrentWorkspace } from '../api/workspaces';
import { downloadDeliveryNotePdf } from '../components/pdf/DeliveryNotePDF';
import { Skeleton } from '../components/Skeleton';
import { DeliveryNoteStatusBadge } from './DeliveryNoteStatusBadge';
import quoteStyles from './Quotations.module.css';
import styles from './DeliveryNotes.module.css';
import inv from './Invoices.module.css';

const STATUSES: DeliveryNoteStatus[] = ['DRAFT', 'CONFIRMED', 'CANCELLED'];

async function parentRefs(row: DeliveryNoteListItem): Promise<{
  lpoNumber?: string;
  invoiceNumber?: string;
}> {
  if (row.customer_purchase_order_id) {
    const lpo = await getLpo(row.customer_purchase_order_id);
    return { lpoNumber: lpo.lpo_number };
  }
  if (row.invoice_id) {
    const invoice = await getInvoice(row.invoice_id);
    return { invoiceNumber: invoice.invoice_number };
  }
  return {};
}

export const DeliveryNotes = () => {
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
    queryKey: ['delivery-notes', { status, clientId, search, page }],
    queryFn: () =>
      getDeliveryNotes({
        page,
        per_page: 20,
        status: (status || undefined) as DeliveryNoteStatus | undefined,
        client_id: clientId || undefined,
        search: search || undefined,
      }),
  });

  const confirmMutation = useMutation({
    mutationFn: confirmDeliveryNote,
    onSuccess: (dn) => {
      queryClient.invalidateQueries({ queryKey: ['delivery-notes'] });
      queryClient.invalidateQueries({ queryKey: ['inventory-levels'] });
      setCreditHoldMessage(null);
      toast.success(`${dn.dn_number} confirmed`);
    },
    onError: (error: unknown) => {
      const parsed = extractApiError(error);
      if (parsed.code === 'CREDIT_HOLD') {
        setCreditHoldMessage(parsed.message);
        toast.error(parsed.message);
      }
    },
  });

  const downloadPdf = async (row: DeliveryNoteListItem) => {
    setPdfBusyId(row.id);
    try {
      const dn = await getDeliveryNote(row.id);
      const client = clients?.find((entry) => entry.id === dn.client_id);
      const refs = await parentRefs(row);
      await downloadDeliveryNotePdf({ dn, client, workspace, ...refs });
    } catch (error) {
      const axiosError = error as { response?: unknown };
      if (!axiosError.response) toast.error('Could not generate Delivery Note PDF');
    } finally {
      setPdfBusyId(null);
    }
  };

  const rows = data?.items ?? [];
  const pagination = data?.pagination;

  return (
    <div className={quoteStyles.container}>
      <div className={quoteStyles.header}>
        <h2>Delivery Notes</h2>
        <button
          className={quoteStyles.primaryBtn}
          data-testid="dn-create"
          onClick={() => navigate('/delivery-notes/new')}
        >
          <Plus size={16} style={{ display: 'inline', marginRight: '0.5rem', verticalAlign: 'middle' }} />
          Create delivery note
        </button>
      </div>

      {creditHoldMessage && (
        <div className={inv.ftaBanner} data-testid="credit-hold" role="alert">
          {creditHoldMessage}
        </div>
      )}

      <div className={quoteStyles.filters}>
        <div className={quoteStyles.filterGroup}>
          <label htmlFor="dn-search">Search</label>
          <input
            id="dn-search"
            data-testid="dn-search"
            placeholder="DN number"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className={quoteStyles.filterGroup}>
          <label htmlFor="dn-status-filter">Status</label>
          <select
            id="dn-status-filter"
            data-testid="dn-status-filter"
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
          <label htmlFor="dn-client-filter">Client</label>
          <select
            id="dn-client-filter"
            data-testid="dn-client-filter"
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
                <th>DN #</th>
                <th>Parent</th>
                <th>Client</th>
                <th>Status</th>
                <th>Delivery date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const client = clients?.find((entry) => entry.id === row.client_id);
                const parentLabel = row.customer_purchase_order_id
                  ? 'LPO'
                  : row.invoice_id
                    ? 'Invoice'
                    : '—';
                return (
                  <tr key={row.id} data-testid={`dn-row-${row.dn_number}`}>
                    <td>
                      <button
                        type="button"
                        className={quoteStyles.numberLink}
                        data-testid={`dn-open-${row.dn_number}`}
                        onClick={() => navigate(`/delivery-notes/${row.id}`)}
                      >
                        {row.dn_number}
                      </button>
                    </td>
                    <td>{parentLabel}</td>
                    <td>{client?.name || 'Unknown Client'}</td>
                    <td><DeliveryNoteStatusBadge status={row.status} /></td>
                    <td>{row.delivery_date}</td>
                    <td>
                      <button
                        className={quoteStyles.actionBtn}
                        title="View"
                        onClick={() => navigate(`/delivery-notes/${row.id}`)}
                      >
                        <Eye size={16} />
                      </button>
                      <button
                        className={quoteStyles.actionBtn}
                        data-testid="dn-download-pdf"
                        title="Download Delivery Note PDF"
                        disabled={pdfBusyId === row.id}
                        onClick={() => void downloadPdf(row)}
                      >
                        <Download size={16} />
                      </button>
                      {row.status === 'DRAFT' && (
                        <>
                          <button
                            className={quoteStyles.actionBtn}
                            data-testid="dn-edit"
                            title="Edit"
                            onClick={() => navigate(`/delivery-notes/${row.id}/edit`)}
                          >
                            <Edit2 size={16} />
                          </button>
                          <button
                            className={quoteStyles.primaryBtn}
                            data-testid="dn-confirm"
                            disabled={confirmMutation.isPending}
                            title={
                              client?.credit_status === 'HOLD' && workspace?.block_do_on_hold
                                ? 'Blocked while this client is on credit HOLD'
                                : 'Confirm'
                            }
                            onClick={() => confirmMutation.mutate(row.id)}
                          >
                            Confirm
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>
                    No delivery notes found.
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
        Delivery notes ship stock from an LPO or an invoice — not inbound GRN receipts.
      </p>
    </div>
  );
};
