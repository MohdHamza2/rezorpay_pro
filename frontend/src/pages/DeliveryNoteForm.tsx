import { useEffect } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { getClients } from '../api/clients';
import {
  createDeliveryNote,
  getDeliveryNote,
  updateDeliveryNote,
} from '../api/deliveryNotes';
import type { DeliveryNoteUpdatePayload } from '../api/deliveryNotes';
import { getInvoices } from '../api/invoices';
import { getWarehouseBins, getWarehouses } from '../api/inventory';
import { getLpo, getLpos } from '../api/lpos';
import { Skeleton } from '../components/Skeleton';
import {
  applyDraftQtys,
  blankDeliveryNoteForm,
  buildDnCreatePayload,
  buildDnUpdatePayload,
  deliveryNoteSchema,
  dnToForm,
  loadInvoiceRemainingLines,
  remainingLpoLines,
  type DeliveryNoteFormValues,
} from './deliveryNoteHelpers';
import inv from './Invoices.module.css';
import quoteStyles from './Quotations.module.css';
import styles from './DeliveryNotes.module.css';

const SHIPPABLE_LPO = new Set(['RECEIVED', 'PARTIAL', 'INVOICED']);

export const DeliveryNoteForm = () => {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
  const { data: warehouses } = useQuery({ queryKey: ['warehouses'], queryFn: getWarehouses });
  const { data: lpoPage } = useQuery({
    queryKey: ['lpos', 'dn-picker'],
    queryFn: () => getLpos({ page: 1, per_page: 100 }),
  });
  const { data: invoices } = useQuery({ queryKey: ['invoices'], queryFn: getInvoices });
  const { data: existing, isLoading: loadingDn } = useQuery({
    queryKey: ['delivery-note', id],
    queryFn: () => getDeliveryNote(id!),
    enabled: Boolean(id),
  });

  const { register, control, handleSubmit, reset, setValue, watch, formState: { errors } } =
    useForm<DeliveryNoteFormValues>({
      resolver: zodResolver(deliveryNoteSchema),
      defaultValues: blankDeliveryNoteForm(),
    });
  const { fields, replace } = useFieldArray({ control, name: 'items' });
  const parentKindField = register('parent_kind');

  const parentKind = watch('parent_kind');
  const lpoId = watch('customer_purchase_order_id');
  const invoiceId = watch('invoice_id');
  const warehouseId = watch('warehouse_id');

  const { data: selectedLpo } = useQuery({
    queryKey: ['lpo', lpoId],
    queryFn: () => getLpo(lpoId!),
    enabled: parentKind === 'lpo' && Boolean(lpoId),
  });
  const { data: invoiceLines } = useQuery({
    queryKey: ['dn-invoice-remaining', invoiceId],
    queryFn: () => loadInvoiceRemainingLines(invoiceId!),
    enabled: parentKind === 'invoice' && Boolean(invoiceId),
  });
  const { data: bins } = useQuery({
    queryKey: ['warehouse-bins', warehouseId],
    queryFn: () => getWarehouseBins(warehouseId!),
    enabled: Boolean(warehouseId),
  });

  useEffect(() => {
    if (!existing) return;
    if (existing.status !== 'DRAFT') {
      toast.error('Only draft delivery notes can be edited');
      navigate(`/delivery-notes/${existing.id}`, { replace: true });
      return;
    }
    reset(dnToForm(existing));
  }, [existing, navigate, reset]);

  useEffect(() => {
    if (parentKind !== 'lpo' || !selectedLpo) return;
    const lines = remainingLpoLines(selectedLpo);
    replace(existing ? applyDraftQtys(lines, existing) : lines);
    const client = clients?.find((entry) => entry.id === selectedLpo.client_id);
    if (client?.address && !existing?.shipping_address) {
      setValue('shipping_address', client.address);
    }
  }, [parentKind, selectedLpo?.id, existing?.id, clients, replace, setValue, selectedLpo, existing]);

  useEffect(() => {
    if (parentKind !== 'invoice' || !invoiceLines) return;
    replace(existing ? applyDraftQtys(invoiceLines, existing) : invoiceLines);
  }, [parentKind, invoiceId, existing?.id, invoiceLines, existing, replace]);

  const createMutation = useMutation({
    mutationFn: createDeliveryNote,
    onSuccess: (dn) => {
      queryClient.invalidateQueries({ queryKey: ['delivery-notes'] });
      toast.success('Delivery note created');
      navigate(`/delivery-notes/${dn.id}`);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ dnId, data }: { dnId: string; data: DeliveryNoteUpdatePayload }) =>
      updateDeliveryNote(dnId, data),
    onSuccess: (dn) => {
      queryClient.invalidateQueries({ queryKey: ['delivery-notes'] });
      queryClient.invalidateQueries({ queryKey: ['delivery-note', dn.id] });
      toast.success('Delivery note updated');
      navigate(`/delivery-notes/${dn.id}`);
    },
  });

  const onSubmit = (data: DeliveryNoteFormValues) => {
    if (isEdit && id) {
      updateMutation.mutate({ dnId: id, data: buildDnUpdatePayload(data) });
      return;
    }
    createMutation.mutate(buildDnCreatePayload(data));
  };

  if (isEdit && loadingDn) {
    return (
      <div className={quoteStyles.container}>
        <Skeleton height="320px" />
      </div>
    );
  }

  const busy = createMutation.isPending || updateMutation.isPending;
  const shippableLpos = (lpoPage?.items ?? []).filter((row) => SHIPPABLE_LPO.has(row.status));
  const shippableInvoices = (invoices ?? []).filter((row) => row.status !== 'CANCELLED');
  const activeWarehouses = (warehouses ?? []).filter((row) => row.is_active);
  const activeBins = (bins ?? []).filter((row) => row.is_active);

  return (
    <div className={quoteStyles.container}>
      <div className={quoteStyles.header}>
        <h2>{isEdit ? 'Edit delivery note' : 'Create delivery note'}</h2>
        <button
          type="button"
          className={quoteStyles.secondaryBtn}
          onClick={() => navigate('/delivery-notes')}
        >
          Back to list
        </button>
      </div>

      <div className={quoteStyles.pageCard} data-testid="dn-form">
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className={inv.grid2}>
            <div className={inv.formGroup} style={{ gridColumn: '1 / -1' }}>
              <span>Parent (exactly one)</span>
              <div className={styles.parentXor}>
                <label>
                  <input
                    type="radio"
                    value="lpo"
                    data-testid="dn-parent-type-lpo"
                    disabled={isEdit}
                    {...parentKindField}
                    onChange={(event) => {
                      void parentKindField.onChange(event);
                      setValue('invoice_id', '');
                      replace([]);
                    }}
                  />
                  LPO remaining
                </label>
                <label>
                  <input
                    type="radio"
                    value="invoice"
                    data-testid="dn-parent-type-invoice"
                    disabled={isEdit}
                    {...parentKindField}
                    onChange={(event) => {
                      void parentKindField.onChange(event);
                      setValue('customer_purchase_order_id', '');
                      replace([]);
                    }}
                  />
                  Invoice remaining
                </label>
              </div>
              <span className={inv.hint}>
                Ship from an LPO or an invoice, not both. Omit a line (qty 0) to leave it undelivered.
              </span>
            </div>

            {parentKind === 'lpo' ? (
              <div className={inv.formGroup}>
                <label htmlFor="dn-lpo">LPO</label>
                <select
                  id="dn-lpo"
                  data-testid="dn-parent-select"
                  disabled={isEdit}
                  {...register('customer_purchase_order_id')}
                >
                  <option value="">Select LPO...</option>
                  {shippableLpos.map((lpo) => (
                    <option key={lpo.id} value={lpo.id}>
                      {lpo.lpo_number}
                      {lpo.customer_po_number ? ` (${lpo.customer_po_number})` : ''}
                    </option>
                  ))}
                </select>
                {errors.customer_purchase_order_id && (
                  <span className={inv.errorText}>{errors.customer_purchase_order_id.message}</span>
                )}
              </div>
            ) : (
              <div className={inv.formGroup}>
                <label htmlFor="dn-invoice">Invoice</label>
                <select
                  id="dn-invoice"
                  data-testid="dn-parent-select"
                  disabled={isEdit}
                  {...register('invoice_id')}
                >
                  <option value="">Select invoice...</option>
                  {shippableInvoices.map((invoice) => (
                    <option key={invoice.id} value={invoice.id}>
                      {invoice.invoice_number}
                    </option>
                  ))}
                </select>
                {errors.invoice_id && (
                  <span className={inv.errorText}>{errors.invoice_id.message}</span>
                )}
              </div>
            )}

            <div className={inv.formGroup}>
              <label htmlFor="dn-warehouse">Warehouse</label>
              <select id="dn-warehouse" data-testid="dn-warehouse" {...register('warehouse_id')}>
                <option value="">Select warehouse...</option>
                {activeWarehouses.map((warehouse) => (
                  <option key={warehouse.id} value={warehouse.id}>
                    {warehouse.code} — {warehouse.name}
                  </option>
                ))}
              </select>
              {errors.warehouse_id && (
                <span className={inv.errorText}>{errors.warehouse_id.message}</span>
              )}
            </div>
            <div className={inv.formGroup}>
              <label htmlFor="dn-bin">Bin (optional)</label>
              <select id="dn-bin" data-testid="dn-bin" {...register('bin_id')} disabled={!warehouseId}>
                <option value="">First active bin</option>
                {activeBins.map((bin) => (
                  <option key={bin.id} value={bin.id}>{bin.code}</option>
                ))}
              </select>
            </div>
            <div className={inv.formGroup}>
              <label htmlFor="dn-delivery-date">Delivery date</label>
              <input
                id="dn-delivery-date"
                type="date"
                data-testid="dn-delivery-date"
                {...register('delivery_date')}
              />
              {errors.delivery_date && (
                <span className={inv.errorText}>{errors.delivery_date.message}</span>
              )}
            </div>
            <div className={inv.formGroup}>
              <label htmlFor="dn-vehicle">Vehicle number</label>
              <input id="dn-vehicle" data-testid="dn-vehicle" {...register('vehicle_number')} />
            </div>
            <div className={inv.formGroup}>
              <label htmlFor="dn-driver">Driver name</label>
              <input id="dn-driver" data-testid="dn-driver" {...register('driver_name')} />
            </div>
            <div className={inv.formGroup} style={{ gridColumn: '1 / -1' }}>
              <label htmlFor="dn-address">Shipping address</label>
              <textarea id="dn-address" rows={2} data-testid="dn-address" {...register('shipping_address')} />
            </div>
            <div className={inv.formGroup} style={{ gridColumn: '1 / -1' }}>
              <label htmlFor="dn-notes">Notes</label>
              <textarea id="dn-notes" rows={2} data-testid="dn-notes" {...register('notes')} />
            </div>
          </div>

          <div className={inv.itemsSection}>
            <div className={inv.itemsHeader}>
              <h4>Remaining lines</h4>
            </div>
            {fields.length === 0 ? (
              <p className={quoteStyles.hint}>Select a parent to load remaining quantity.</p>
            ) : (
              <div className={quoteStyles.tableContainer}>
                <table className={quoteStyles.table}>
                  <thead>
                    <tr>
                      <th>Description</th>
                      <th>SKU</th>
                      <th>Ordered</th>
                      <th>Delivered</th>
                      <th>Remaining</th>
                      <th>Qty to ship</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fields.map((field, index) => (
                      <tr key={field.id}>
                        <td>
                          {field.description}
                          <input type="hidden" {...register(`items.${index}.parent_item_id`)} />
                          <input type="hidden" {...register(`items.${index}.description`)} />
                          <input type="hidden" {...register(`items.${index}.sku`)} />
                          <input type="hidden" {...register(`items.${index}.ordered`)} />
                          <input type="hidden" {...register(`items.${index}.delivered`)} />
                          <input type="hidden" {...register(`items.${index}.remaining`)} />
                        </td>
                        <td>{field.sku || '—'}</td>
                        <td>{field.ordered}</td>
                        <td>{field.delivered}</td>
                        <td data-testid={`dn-remaining-${index}`}>{field.remaining}</td>
                        <td>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            className={styles.qtyInput}
                            data-testid={`dn-qty-${index}`}
                            {...register(`items.${index}.quantity`)}
                          />
                          {errors.items?.[index]?.quantity && (
                            <span className={inv.errorText}>{errors.items[index].quantity.message}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {errors.items?.root && <span className={inv.errorText}>{errors.items.root.message}</span>}
            {errors.items?.message && <span className={inv.errorText}>{errors.items.message}</span>}
          </div>

          <div className={inv.modalActions}>
            <button
              type="button"
              className={inv.secondaryBtn}
              onClick={() => navigate(isEdit && id ? `/delivery-notes/${id}` : '/delivery-notes')}
            >
              Cancel
            </button>
            <button
              type="submit"
              className={inv.primaryBtn}
              data-testid="dn-form-submit"
              disabled={busy}
            >
              {isEdit ? 'Update delivery note' : 'Create delivery note'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
