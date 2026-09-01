import { useEffect } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate, useParams } from 'react-router-dom';
import { Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { getClients } from '../api/clients';
import { createLpo, getLpo, updateLpo } from '../api/lpos';
import type { LpoUpdatePayload } from '../api/lpos';
import { getProducts, PRODUCT_PAGE_SIZE } from '../api/products';
import { LinePriceSource, useCatalogLinePricing } from './catalogLinePricing';
import { Skeleton } from '../components/Skeleton';
import {
  blankLpoForm,
  buildLpoCreatePayload,
  buildLpoUpdatePayload,
  emptyLpoLine,
  lpoSchema,
  lpoToForm,
  type LpoFormValues,
} from './lpoHelpers';
import inv from './Invoices.module.css';
import quoteStyles from './Quotations.module.css';

export const LpoForm = () => {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
  const { data: productPage } = useQuery({
    queryKey: ['products', 'lpo-picker'],
    queryFn: () => getProducts({ page: 1, per_page: PRODUCT_PAGE_SIZE, is_active: true }),
  });
  const { data: existing, isLoading: loadingLpo } = useQuery({
    queryKey: ['lpo', id],
    queryFn: () => getLpo(id!),
    enabled: Boolean(id),
  });

  const { register, control, handleSubmit, reset, setValue, getValues, formState: { errors } } =
    useForm<LpoFormValues>({
      resolver: zodResolver(lpoSchema),
      defaultValues: blankLpoForm(),
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
      toast.error('Only draft LPOs can be edited');
      navigate(`/lpos/${existing.id}`, { replace: true });
      return;
    }
    reset(lpoToForm(existing));
  }, [existing, navigate, reset]);

  const createMutation = useMutation({
    mutationFn: createLpo,
    onSuccess: (lpo) => {
      queryClient.invalidateQueries({ queryKey: ['lpos'] });
      toast.success('LPO created');
      navigate(`/lpos/${lpo.id}`);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ lpoId, data }: { lpoId: string; data: LpoUpdatePayload }) =>
      updateLpo(lpoId, data),
    onSuccess: (lpo) => {
      queryClient.invalidateQueries({ queryKey: ['lpos'] });
      queryClient.invalidateQueries({ queryKey: ['lpo', lpo.id] });
      toast.success('LPO updated');
      navigate(`/lpos/${lpo.id}`);
    },
  });

  const onSubmit = (data: LpoFormValues) => {
    if (isEdit && id) {
      updateMutation.mutate({ lpoId: id, data: buildLpoUpdatePayload(data) });
      return;
    }
    createMutation.mutate(buildLpoCreatePayload(data));
  };

  if (isEdit && loadingLpo) {
    return (
      <div className={quoteStyles.container}>
        <Skeleton height="320px" />
      </div>
    );
  }

  const busy = createMutation.isPending || updateMutation.isPending;
  const clientField = register('client_id');

  return (
    <div className={quoteStyles.container}>
      <div className={quoteStyles.header}>
        <h2>{isEdit ? 'Edit LPO' : 'Create LPO'}</h2>
        <button type="button" className={quoteStyles.secondaryBtn} onClick={() => navigate('/lpos')}>
          Back to list
        </button>
      </div>

      <div className={quoteStyles.pageCard} data-testid="lpo-form">
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className={inv.grid2}>
            <div className={inv.formGroup}>
              <label htmlFor="lpo-client">Client</label>
              <select
                id="lpo-client"
                data-testid="lpo-client-select"
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
              <label htmlFor="lpo-customer-po">Customer PO number</label>
              <input
                id="lpo-customer-po"
                data-testid="lpo-customer-po-input"
                placeholder="Contractor PO (optional)"
                {...register('customer_po_number')}
              />
              <span className={inv.hint}>The customer’s own PO. Internal LPO-YYYY-XXXX is assigned on save.</span>
              {errors.customer_po_number && (
                <span className={inv.errorText}>{errors.customer_po_number.message}</span>
              )}
            </div>
            <div className={inv.formGroup}>
              <label htmlFor="lpo-date">LPO date</label>
              <input id="lpo-date" type="date" data-testid="lpo-date" {...register('lpo_date')} />
              {errors.lpo_date && <span className={inv.errorText}>{errors.lpo_date.message}</span>}
            </div>
            <div className={inv.formGroup}>
              <label htmlFor="lpo-expected-delivery">Expected delivery</label>
              <input
                id="lpo-expected-delivery"
                type="date"
                data-testid="lpo-expected-delivery"
                {...register('expected_delivery_date')}
              />
              {errors.expected_delivery_date && (
                <span className={inv.errorText}>{errors.expected_delivery_date.message}</span>
              )}
            </div>
            <div className={inv.formGroup} style={{ gridColumn: '1 / -1' }}>
              <label htmlFor="lpo-notes">Notes</label>
              <textarea id="lpo-notes" rows={3} data-testid="lpo-notes" {...register('notes')} />
            </div>
          </div>

          <div className={inv.itemsSection}>
            <div className={inv.itemsHeader}>
              <h4>Line Items</h4>
              <button
                type="button"
                className={inv.secondaryBtn}
                data-testid="lpo-add-item"
                onClick={() => append(emptyLpoLine())}
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
                        data-testid={`lpo-item-${index}-product`}
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
                        data-testid={`lpo-item-${index}-description`}
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
                        data-testid={`lpo-item-${index}-quantity`}
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
                        data-testid={`lpo-item-${index}-price`}
                        {...priceField}
                        onChange={(event) => {
                          void priceField.onChange(event);
                          pricing.onPriceInput(index);
                        }}
                      />
                      <LinePriceSource
                        testId={`lpo-item-${index}-price-source`}
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
                        data-testid={`lpo-item-${index}-tax`}
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
              onClick={() => navigate(isEdit && id ? `/lpos/${id}` : '/lpos')}
            >
              Cancel
            </button>
            <button
              type="submit"
              className={inv.primaryBtn}
              data-testid="lpo-form-submit"
              disabled={busy}
            >
              {isEdit ? 'Update LPO' : 'Create LPO'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
