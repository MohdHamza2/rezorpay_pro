import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { extractApiError, isHttpNotFound } from '../api/errors';
import { getClients } from '../api/clients';
import {
  cancelDeliveryNote,
  confirmDeliveryNote,
  deleteDeliveryNote,
  getDeliveryNote,
} from '../api/deliveryNotes';
import { getInvoice } from '../api/invoices';
import { getWarehouses } from '../api/inventory';
import { getLpo } from '../api/lpos';
import { getCurrentWorkspace } from '../api/workspaces';
import { downloadDeliveryNotePdf } from '../components/pdf/DeliveryNotePDF';
import { DeliveryNotePdfPreview } from '../components/pdf/DeliveryNotePdfPreview';
import { Skeleton } from '../components/Skeleton';
import { formatQty, undeliveredQty } from './deliveryNoteHelpers';
import { DeliveryNoteStatusBadge } from './DeliveryNoteStatusBadge';
import quoteStyles from './Quotations.module.css';
import inv from './Invoices.module.css';

export const DeliveryNoteDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [creditHoldMessage, setCreditHoldMessage] = useState<string | null>(null);

  const { data: dn, isLoading, isError, error } = useQuery({
    queryKey: ['delivery-note', id],
    queryFn: () => getDeliveryNote(id!),
    enabled: Boolean(id),
    retry: (count, err) => !isHttpNotFound(err) && count < 2,
  });
  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
  const { data: workspace } = useQuery({ queryKey: ['workspace'], queryFn: getCurrentWorkspace });
  const { data: warehouses } = useQuery({ queryKey: ['warehouses'], queryFn: getWarehouses });
  const { data: linkedLpo } = useQuery({
    queryKey: ['lpo', dn?.customer_purchase_order_id],
    queryFn: () => getLpo(dn!.customer_purchase_order_id!),
    enabled: Boolean(dn?.customer_purchase_order_id),
  });
  const { data: linkedInvoice } = useQuery({
    queryKey: ['invoice', dn?.invoice_id],
    queryFn: () => getInvoice(dn!.invoice_id!),
    enabled: Boolean(dn?.invoice_id),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['delivery-notes'] });
    queryClient.invalidateQueries({ queryKey: ['delivery-note', id] });
    queryClient.invalidateQueries({ queryKey: ['inventory-levels'] });
  };

  const confirmMutation = useMutation({
    mutationFn: confirmDeliveryNote,
    onSuccess: () => {
      invalidate();
      setCreditHoldMessage(null);
      toast.success('Delivery note confirmed');
    },
    onError: (err: unknown) => {
      const parsed = extractApiError(err);
      if (parsed.code === 'CREDIT_HOLD') {
        setCreditHoldMessage(parsed.message);
        toast.error(parsed.message);
      }
    },
  });
  const cancelMutation = useMutation({
    mutationFn: ({ dnId, reason }: { dnId: string; reason?: string }) =>
      cancelDeliveryNote(dnId, reason),
    onSuccess: () => {
      invalidate();
      toast.success('Delivery note cancelled');
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteDeliveryNote,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['delivery-notes'] });
      toast.success('Delivery note deleted');
      navigate('/delivery-notes');
    },
  });

  const client = clients?.find((entry) => entry.id === dn?.client_id);
  const warehouse = warehouses?.find((entry) => entry.id === dn?.warehouse_id);
  const busy = confirmMutation.isPending || cancelMutation.isPending || deleteMutation.isPending;

  const handleCancel = () => {
    if (!dn) return;
    const reason = window.prompt('Cancellation reason (optional)');
    if (reason === null) return;
    cancelMutation.mutate({ dnId: dn.id, reason: reason.trim() || undefined });
  };

  const handleDelete = () => {
    if (!dn) return;
    if (!window.confirm('Delete this draft delivery note?')) return;
    deleteMutation.mutate(dn.id);
  };

  const handleDownload = async () => {
    if (!dn) return;
    setPdfBusy(true);
    try {
      const fresh = await getDeliveryNote(dn.id);
      await downloadDeliveryNotePdf({
        dn: fresh,
        client,
        workspace,
        lpoNumber: linkedLpo?.lpo_number,
        invoiceNumber: linkedInvoice?.invoice_number,
      });
    } catch (err) {
      const axiosError = err as { response?: unknown };
      if (!axiosError.response) toast.error('Could not generate Delivery Note PDF');
    } finally {
      setPdfBusy(false);
    }
  };

  if (isError && isHttpNotFound(error)) {
    return (
      <div className={quoteStyles.container}>
        <p data-testid="dn-not-found">Delivery note not found.</p>
      </div>
    );
  }

  if (isLoading || !dn) {
    return (
      <div className={quoteStyles.container}>
        {isLoading ? <Skeleton height="320px" /> : <p>Delivery note not found.</p>}
      </div>
    );
  }

  return (
    <div className={quoteStyles.container} data-testid="dn-detail">
      <div className={quoteStyles.header}>
        <h2 data-testid="dn-number">{dn.dn_number}</h2>
        <button
          type="button"
          className={quoteStyles.secondaryBtn}
          onClick={() => navigate('/delivery-notes')}
        >
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
          <DeliveryNoteStatusBadge status={dn.status} />
          <button
            type="button"
            className={quoteStyles.secondaryBtn}
            data-testid="dn-preview-pdf"
            onClick={() => setPreviewOpen(true)}
          >
            Preview PDF
          </button>
          <button
            type="button"
            className={quoteStyles.secondaryBtn}
            data-testid="dn-download-pdf"
            disabled={pdfBusy}
            onClick={() => void handleDownload()}
          >
            Download PDF
          </button>
          {dn.status === 'DRAFT' && (
            <>
              <button
                type="button"
                className={quoteStyles.secondaryBtn}
                data-testid="dn-edit"
                onClick={() => navigate(`/delivery-notes/${dn.id}/edit`)}
              >
                Edit
              </button>
              <button
                type="button"
                className={quoteStyles.primaryBtn}
                data-testid="dn-confirm"
                disabled={busy}
                title={
                  client?.credit_status === 'HOLD' && workspace?.block_do_on_hold
                    ? 'Blocked while this client is on credit HOLD'
                    : 'Confirm'
                }
                onClick={() => confirmMutation.mutate(dn.id)}
              >
                Confirm
              </button>
              <button
                type="button"
                className={quoteStyles.dangerBtn}
                data-testid="dn-delete"
                disabled={busy}
                onClick={handleDelete}
              >
                Delete
              </button>
            </>
          )}
          {dn.status === 'CONFIRMED' && (
            <button
              type="button"
              className={quoteStyles.dangerBtn}
              data-testid="dn-cancel"
              disabled={busy}
              onClick={handleCancel}
            >
              Cancel delivery
            </button>
          )}
        </div>

        <div className={quoteStyles.metaGrid}>
          <div>
            <span className={quoteStyles.metaLabel}>DN number</span>
            <div className={quoteStyles.metaValue}>{dn.dn_number}</div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Client</span>
            <div className={quoteStyles.metaValue}>{client?.name || 'Unknown Client'}</div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Parent</span>
            <div className={quoteStyles.metaValue}>
              {linkedLpo
                ? `LPO ${linkedLpo.lpo_number}`
                : linkedInvoice
                  ? `Invoice ${linkedInvoice.invoice_number}`
                  : '—'}
            </div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Warehouse</span>
            <div className={quoteStyles.metaValue}>
              {warehouse ? `${warehouse.code} — ${warehouse.name}` : dn.warehouse_id}
            </div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Delivery date</span>
            <div className={quoteStyles.metaValue}>{dn.delivery_date}</div>
          </div>
          <div>
            <span className={quoteStyles.metaLabel}>Vehicle / driver</span>
            <div className={quoteStyles.metaValue}>
              {[dn.vehicle_number, dn.driver_name].filter(Boolean).join(' / ') || '—'}
            </div>
          </div>
        </div>

        {dn.shipping_address ? (
          <p className={quoteStyles.hint}><strong>Shipping:</strong> {dn.shipping_address}</p>
        ) : null}
        {dn.notes ? (
          <p className={quoteStyles.hint}><strong>Notes:</strong> {dn.notes}</p>
        ) : null}
        {dn.cancellation_reason ? (
          <p className={quoteStyles.hint}><strong>Cancellation reason:</strong> {dn.cancellation_reason}</p>
        ) : null}

        <div className={quoteStyles.tableContainer}>
          <table className={quoteStyles.table}>
            <thead>
              <tr>
                <th>Description</th>
                <th>SKU</th>
                <th>Qty</th>
              </tr>
            </thead>
            <tbody>
              {(dn.items ?? []).map((item) => (
                <tr key={item.id}>
                  <td>{item.description}</td>
                  <td>{item.sku_snapshot || '—'}</td>
                  <td>{formatQty(item.quantity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {linkedLpo?.items && linkedLpo.items.length > 0 && (
          <div style={{ marginTop: '1.5rem' }}>
            <h4>LPO delivered vs ordered</h4>
            <div className={quoteStyles.tableContainer}>
              <table className={quoteStyles.table}>
                <thead>
                  <tr>
                    <th>Description</th>
                    <th>Ordered</th>
                    <th>Delivered</th>
                    <th>Remaining</th>
                  </tr>
                </thead>
                <tbody>
                  {linkedLpo.items.map((item) => (
                    <tr key={item.id}>
                      <td>{item.description}</td>
                      <td>{formatQty(item.quantity)}</td>
                      <td>{formatQty(item.quantity_delivered)}</td>
                      <td>{formatQty(undeliveredQty(item))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {previewOpen && (
        <DeliveryNotePdfPreview
          dn={dn}
          client={client}
          workspace={workspace}
          lpoNumber={linkedLpo?.lpo_number}
          invoiceNumber={linkedInvoice?.invoice_number}
          onClose={() => setPreviewOpen(false)}
        />
      )}
    </div>
  );
};
