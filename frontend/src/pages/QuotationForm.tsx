import { useEffect } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate, useParams } from 'react-router-dom';
import { Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { getClients } from '../api/clients';
import { createQuotation, getQuotation, updateQuotation } from '../api/quotations';
import type { QuotationUpdatePayload } from '../api/quotations';
import { getProducts, PRODUCT_PAGE_SIZE } from '../api/products';
import { LinePriceSource, useCatalogLinePricing } from './catalogLinePricing';
import { Skeleton } from '../components/Skeleton';
import {
  blankQuotationForm,
  buildCreatePayload,
  buildUpdatePayload,
  emptyLine,
  quotationSchema,
  quoteToForm,
  type QuotationFormValues,
} from './quotationHelpers';
import inv from './Invoices.module.css';
import styles from './Quotations.module.css';

export const QuotationForm = () => {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
  const { data: productPage } = useQuery({
    queryKey: ['products', 'quotation-picker'],
    queryFn: () => getProducts({ page: 1, per_page: PRODUCT_PAGE_SIZE, is_active: true }),
  });
  const { data: existing, isLoading: loadingQuote } = useQuery({
    queryKey: ['quotation', id],
    queryFn: () => getQuotation(id!),
    enabled: Boolean(id),
  });

  const { register, control, handleSubmit, reset, setValue, getValues, formState: { errors } } =
    useForm<QuotationFormValues>({
      resolver: zodResolver(quotationSchema),
      defaultValues: blankQuotationForm(),
    });
  const { fields, append, remove } = useFieldArray({ control, name: 'items' });
  const pricing = useCatalogLinePricing({
    fieldIds: fields.map((field) => field.id),
    getClientId: () => getValues('client_id'),
    getLine: (index) => {
      const line = getValues('items')[index];
      return { product_id: line?.product_id, quantity: line?.quantity ?? '' };
    },
    setUnitPrice: (index, value) => setValue(`items.${index}.unit_price`, value),
    setDescription: (index, value) => setValue(`items.${index}.description`, value),
    productName: (productId) =>
      productPage?.items.find((product) => product.id === productId)?.name,
  });

  useEffect(() => {
    if (!existing) return;
    if (existing.status !== 'DRAFT') {
      toast.error('Only draft quotations can be edited');
      navigate(`/quotations/${existing.id}`, { replace: true });
      return;
    }
    reset(quoteToForm(existing));
  }, [existing, navigate, reset]);

  const createMutation = useMutation({
    mutationFn: createQuotation,
    onSuccess: (quote) => {
      queryClient.invalidateQueries({ queryKey: ['quotations'] });
      toast.success('Quotation created');
      navigate(`/quotations/${quote.id}`);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ quoteId, data }: { quoteId: string; data: QuotationUpdatePayload }) =>
      updateQuotation(quoteId, data),
    onSuccess: (quote) => {
      queryClient.invalidateQueries({ queryKey: ['quotations'] });
      queryClient.invalidateQueries({ queryKey: ['quotation', quote.id] });
      toast.success('Quotation updated');
      navigate(`/quotations/${quote.id}`);
    },
  });

  const onSubmit = (data: QuotationFormValues) => {
    if (isEdit && id) {
      updateMutation.mutate({ quoteId: id, data: buildUpdatePayload(data) });
      return;
    }
    createMutation.mutate(buildCreatePayload(data));
  };

  if (isEdit && loadingQuote) {
    return (
      <div className={styles.container}>
        <Skeleton height="320px" />
      </div>
    );
  }

  const busy = createMutation.isPending || updateMutation.isPending;
  const clientField = register('client_id');

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>{isEdit ? 'Edit Quotation' : 'Create Quotation'}</h2>
        <button type="button" className={styles.secondaryBtn} onClick={() => navigate('/quotations')}>
          Back to list
        </button>
      </div>

      <div className={styles.pageCard} data-testid="quotation-form">
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className={inv.grid2}>
            <div className={inv.formGroup}>
              <label htmlFor="quotation-client">Client</label>
              <select
                id="quotation-client"
                data-testid="quotation-client-select"
                {...clientField}
                disabled={isEdit}
                onChange={(event) => {
                  void clientField.onChange(event);
                  pricing.onHeaderClientChange(event.target.value);
                }}
              >
                <option value="">Select a client...</option>
                {clients?.map((client) => (
                  <option key={client.id} value={client.id}>{client.name}</option>
                ))}
              </select>
              {errors.client_id && <span className={inv.errorText}>{errors.client_id.message}</span>}
            </div>
            <div className={inv.formGroup}>
              <label>Currency</label>
              <span className={inv.currencyLabel}>AED</span>
            </div>
            <div className={inv.formGroup}>
              <label htmlFor="quotation-date">Quotation date</label>
              <input
                id="quotation-date"
                type="date"
                data-testid="quotation-date"
                {...register('quotation_date')}
              />
              {errors.quotation_date && (
                <span className={inv.errorText}>{errors.quotation_date.message}</span>
              )}
            </div>
            <div className={inv.formGroup}>
              <label htmlFor="quotation-valid-until">Valid until</label>
              <input
                id="quotation-valid-until"
                type="date"
                data-testid="quotation-valid-until"
                {...register('valid_until')}
              />
              <span className={inv.hint}>Defaults to quotation date + 14 days.</span>
              {errors.valid_until && (
                <span className={inv.errorText}>{errors.valid_until.message}</span>
              )}
            </div>
            <div className={inv.formGroup} style={{ gridColumn: '1 / -1' }}>
              <label htmlFor="quotation-notes">Notes</label>
              <textarea
                id="quotation-notes"
                rows={3}
                data-testid="quotation-notes"
                {...register('notes')}
              />
            </div>
          </div>

          <div className={inv.itemsSection}>
            <div className={inv.itemsHeader}>
              <h4>Line Items</h4>
              <button
                type="button"
                className={inv.secondaryBtn}
                data-testid="quotation-add-item"
                onClick={() => append(emptyLine())}
              >
                Add Item
              </button>
            </div>
            {fields.map((field, index) => {
              const productField = register(`items.${index}.product_id` as const);
              const qtyField = register(`items.${index}.quantity` as const);
              const priceField = register(`items.${index}.unit_price` as const);
              return (
                <div key={field.id} className={inv.itemRow}>
                  <div className={inv.itemRowMain}>
                    <div className={inv.formGroup}>
                      <label>Product (optional)</label>
                      <select
                        data-testid={`quotation-item-${index}-product`}
                        {...productField}
                        onChange={(event) => {
                          void productField.onChange(event);
                          pricing.onProductPick(index, event.target.value);
                        }}
                      >
                        <option value="">Ad-hoc (name / qty / price)</option>
                        {productPage?.items.map((product) => (
                          <option key={product.id} value={product.id}>
                            {product.internal_sku} — {product.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className={inv.formGroup}>
                      <label>Description</label>
                      <input
                        data-testid={`quotation-item-${index}-description`}
                        {...register(`items.${index}.description` as const)}
                      />
                      {errors.items?.[index]?.description && (
                        <span className={inv.errorText}>{errors.items[index].description.message}</span>
                      )}
                    </div>
                  </div>
                  <div className={inv.itemRowNums}>
                    <div className={inv.formGroup}>
                      <label>Qty</label>
                      <input
                        type="number"
                        step="0.01"
                        data-testid={`quotation-item-${index}-quantity`}
                        {...qtyField}
                        onChange={(event) => {
                          void qtyField.onChange(event);
                          pricing.onQuantityChange(index, event.target.value);
                        }}
                      />
                      {errors.items?.[index]?.quantity && (
                        <span className={inv.errorText}>{errors.items[index].quantity.message}</span>
                      )}
                    </div>
                    <div className={inv.formGroup}>
                      <label>Price (AED)</label>
                      <input
                        type="number"
                        step="0.01"
                        data-testid={`quotation-item-${index}-price`}
                        {...priceField}
                        onChange={(event) => {
                          void priceField.onChange(event);
                          pricing.onPriceInput(index);
                        }}
                      />
                      <LinePriceSource
                        testId={`quotation-item-${index}-price-source`}
                        source={pricing.sourceFor(index)}
                        className={inv.priceSource}
                      />
                      {errors.items?.[index]?.unit_price && (
                        <span className={inv.errorText}>{errors.items[index].unit_price.message}</span>
                      )}
                    </div>
                    <div className={inv.formGroup}>
                      <label>Disc %</label>
                      <input
                        type="number"
                        step="0.01"
                        {...register(`items.${index}.discount_percent` as const)}
                      />
                      {errors.items?.[index]?.discount_percent && (
                        <span className={inv.errorText}>
                          {errors.items[index].discount_percent.message}
                        </span>
                      )}
                    </div>
                    <div className={inv.formGroup}>
                      <label>Disc AED</label>
                      <input
                        type="number"
                        step="0.01"
                        {...register(`items.${index}.discount_amount` as const)}
                      />
                    </div>
                    <div className={inv.formGroup}>
                      <label>VAT %</label>
                      <input
                        type="number"
                        step="0.01"
                        placeholder="Inherit"
                        data-testid={`quotation-item-${index}-tax`}
                        {...register(`items.${index}.tax_rate` as const)}
                      />
                      <span className={inv.hint}>Blank inherits 5% (or product rate).</span>
                      {errors.items?.[index]?.tax_rate && (
                        <span className={inv.errorText}>{errors.items[index].tax_rate.message}</span>
                      )}
                    </div>
                    <button
                      type="button"
                      className={inv.removeBtn}
                      onClick={() => remove(index)}
                      disabled={fields.length === 1}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              );
            })}
            {errors.items?.root && <span className={inv.errorText}>{errors.items.root.message}</span>}
            {errors.items?.message && <span className={inv.errorText}>{errors.items.message}</span>}
          </div>

          <div className={inv.modalActions}>
            <button
              type="button"
              className={inv.secondaryBtn}
              onClick={() => navigate(isEdit && id ? `/quotations/${id}` : '/quotations')}
            >
              Cancel
            </button>
            <button
              type="submit"
              className={inv.primaryBtn}
              data-testid="quotation-form-submit"
              disabled={busy}
            >
              {isEdit ? 'Update Quotation' : 'Create Quotation'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
