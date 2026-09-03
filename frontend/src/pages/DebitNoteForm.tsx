import { useEffect } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  createTaxDebitNote,
  getTaxDebitNote,
  updateTaxDebitNote,
} from '../api/debitNotes';
import type { TaxDebitNoteUpdatePayload } from '../api/debitNotes';
import { getInvoice, getInvoices } from '../api/invoices';
import { Skeleton } from '../components/Skeleton';
import {
  applyDraftQtys,
  blankDebitNoteForm,
  buildCnCreatePayload,
  buildCnUpdatePayload,
  cnToForm,
  TAX_DEBIT_NOTE_REASONS,
  taxDebitNoteSchema,
  isCreditableStatus,
  loadCreditRemainingLines,
  REASON_LABELS,
  type DebitNoteFormValues,
} from './debitNoteHelpers';
import inv from './Invoices.module.css';
import quoteStyles from './Quotations.module.css';
import styles from './DebitNotes.module.css';
import { formatAed } from './quotationHelpers';

export const DebitNoteForm = () => {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const presetInvoiceId = searchParams.get('invoice_id') || '';

  const { data: invoices } = useQuery({ queryKey: ['invoices'], queryFn: getInvoices });
  const { data: existing, isLoading: loadingCn } = useQuery({
    queryKey: ['debit-note', id],
    queryFn: () => getTaxDebitNote(id!),
    enabled: Boolean(id),
  });

  const { register, control, handleSubmit, reset, watch, formState: { errors } } =
    useForm<DebitNoteFormValues>({
      resolver: zodResolver(taxDebitNoteSchema),
      defaultValues: blankDebitNoteForm(presetInvoiceId),
    });
  const { fields, replace } = useFieldArray({ control, name: 'items' });
  const invoiceField = register('invoice_id');
  const invoiceId = watch('invoice_id');

  const { data: parentInvoice } = useQuery({
    queryKey: ['invoice', invoiceId],
    queryFn: () => getInvoice(invoiceId),
    enabled: Boolean(invoiceId),
  });
  const { data: remainingLines, error: remainingError } = useQuery({
    queryKey: ['tdn-invoice-remaining', invoiceId],
    queryFn: () => loadCreditRemainingLines(invoiceId),
    enabled: Boolean(invoiceId),
  });

  useEffect(() => {
    if (!existing) return;
    if (existing.status !== 'DRAFT') {
      toast.error('Only draft debit notes can be edited');
      navigate(`/debit-notes/${existing.id}`, { replace: true });
      return;
    }
    reset(cnToForm(existing));
  }, [existing, navigate, reset]);

  useEffect(() => {
    if (!invoiceId || !remainingLines) return;
    replace(existing ? applyDraftQtys(remainingLines, existing) : remainingLines);
  }, [invoiceId, remainingLines, existing, replace]);

  const createMutation = useMutation({
    mutationFn: createTaxDebitNote,
    onSuccess: (cn) => {
      queryClient.invalidateQueries({ queryKey: ['debit-notes'] });
      toast.success('Debit note created');
      navigate(`/debit-notes/${cn.id}`);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ cnId, data }: { cnId: string; data: TaxDebitNoteUpdatePayload }) =>
      updateTaxDebitNote(cnId, data),
    onSuccess: (cn) => {
      queryClient.invalidateQueries({ queryKey: ['debit-notes'] });
      queryClient.invalidateQueries({ queryKey: ['debit-note', cn.id] });
      toast.success('Debit note updated');
      navigate(`/debit-notes/${cn.id}`);
    },
  });

  const onSubmit = (data: DebitNoteFormValues) => {
    if (parentInvoice && !isCreditableStatus(parentInvoice.status)) {
      toast.error('Debit notes require a SENT, PAID, PARTIALLY_PAID, or OVERDUE invoice');
      return;
    }
    if (isEdit && id) {
      updateMutation.mutate({ cnId: id, data: buildCnUpdatePayload(data) });
      return;
    }
    createMutation.mutate(buildCnCreatePayload(data));
  };

  if (isEdit && loadingCn) {
    return (
      <div className={quoteStyles.container}>
        <Skeleton height="320px" />
      </div>
    );
  }

  const busy = createMutation.isPending || updateMutation.isPending;
  const creditable = (invoices ?? []).filter((row) => isCreditableStatus(row.status));

  return (
    <div className={quoteStyles.container}>
      <div className={quoteStyles.header}>
        <h2>{isEdit ? 'Edit debit note' : 'Create debit note'}</h2>
        <button
          type="button"
          className={quoteStyles.secondaryBtn}
          onClick={() => navigate('/debit-notes')}
        >
          Back to list
        </button>
      </div>

      <div className={quoteStyles.pageCard} data-testid="tdn-form">
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className={inv.grid2}>
            <div className={inv.formGroup}>
              <label htmlFor="tdn-invoice">Tax invoice</label>
              <select
                id="tdn-invoice"
                data-testid="tdn-invoice-select"
                disabled={isEdit}
                {...invoiceField}
                onChange={(event) => {
                  void invoiceField.onChange(event);
                  replace([]);
                }}
              >
                <option value="">Select invoice...</option>
                {creditable.map((invoice) => (
                  <option key={invoice.id} value={invoice.id}>
                    {invoice.invoice_number}
                  </option>
                ))}
              </select>
              {errors.invoice_id && (
                <span className={inv.errorText}>{errors.invoice_id.message}</span>
              )}
              <span className={inv.hint}>
                SENT, PAID, PARTIALLY_PAID, or OVERDUE only. DRAFT and CANCELLED cannot be credited.
              </span>
            </div>
            <div className={inv.formGroup}>
              <label htmlFor="tdn-reason">Reason</label>
              <select id="tdn-reason" data-testid="tdn-reason" {...register('reason')}>
                {TAX_DEBIT_NOTE_REASONS.map((reason) => (
                  <option key={reason} value={reason}>{REASON_LABELS[reason]}</option>
                ))}
              </select>
            </div>
            <div className={inv.formGroup}>
              <label htmlFor="tdn-issue-date">Issue date</label>
              <input
                id="tdn-issue-date"
                type="date"
                data-testid="tdn-issue-date"
                {...register('issue_date')}
              />
              {errors.issue_date && (
                <span className={inv.errorText}>{errors.issue_date.message}</span>
              )}
            </div>
            <div className={inv.formGroup} style={{ gridColumn: '1 / -1' }}>
              <label htmlFor="tdn-reason-notes">Reason notes (optional)</label>
              <textarea
                id="tdn-reason-notes"
                rows={2}
                data-testid="tdn-reason-notes"
                {...register('reason_notes')}
              />
            </div>
          </div>

          {parentInvoice ? (
            <p className={quoteStyles.hint}>
              Invoice {parentInvoice.invoice_number} · due {formatAed(parentInvoice.balance_due)}
              {parentInvoice.amount_credited != null
                ? ` · already credited ${formatAed(parentInvoice.amount_credited)}`
                : ''}
              . Prices and VAT rates are copied from the tax invoice.
            </p>
          ) : null}

          <div className={inv.itemsSection}>
            <div className={inv.itemsHeader}>
              <h4>Invoice lines</h4>
            </div>
            {remainingError ? (
              <p style={{ color: 'red', fontWeight: 'bold' }}>Error loading lines: {(remainingError as Error).message}</p>
            ) : fields.length === 0 ? (
              <p className={quoteStyles.hint}>Select an invoice to load remaining quantity.</p>
            ) : (
              <div className={quoteStyles.tableContainer}>
                <table className={quoteStyles.table}>
                  <thead>
                    <tr>
                      <th>Description</th>
                      <th>SKU</th>
                      <th>Invoiced</th>
                      <th>Issued CNs</th>
                      <th>Remaining</th>
                      <th>Qty to credit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fields.map((field, index) => (
                      <tr key={field.id}>
                        <td>
                          {field.description}
                          {field.has_amount_discount ? (
                            <span className={inv.hint}> Amount discount — credit remaining in full.</span>
                          ) : null}
                          <input type="hidden" {...register(`items.${index}.invoice_item_id`)} />
                          <input type="hidden" {...register(`items.${index}.description`)} />
                          <input type="hidden" {...register(`items.${index}.sku`)} />
                          <input type="hidden" {...register(`items.${index}.ordered`)} />
                          <input type="hidden" {...register(`items.${index}.credited`)} />
                          <input type="hidden" {...register(`items.${index}.remaining`)} />
                        </td>
                        <td>{field.sku || '—'}</td>
                        <td>{field.ordered}</td>
                        <td>{field.credited}</td>
                        <td data-testid={`tdn-remaining-${index}`}>{field.remaining}</td>
                        <td>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            className={styles.qtyInput}
                            data-testid={`tdn-qty-${index}`}
                            {...register(`items.${index}.quantity`)}
                          />
                          {errors.items?.[index]?.quantity && (
                            <span className={inv.errorText} data-testid={`tdn-qty-error-${index}`}>
                              {errors.items[index].quantity.message}
                            </span>
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
              onClick={() => navigate(isEdit && id ? `/debit-notes/${id}` : '/debit-notes')}
            >
              Cancel
            </button>
            <button
              type="submit"
              className={inv.primaryBtn}
              data-testid="tdn-form-submit"
              disabled={busy}
            >
              {isEdit ? 'Update debit note' : 'Create debit note'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
