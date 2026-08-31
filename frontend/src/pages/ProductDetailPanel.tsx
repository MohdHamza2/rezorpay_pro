import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import toast from 'react-hot-toast';
import { Trash2 } from 'lucide-react';
import { getClients } from '../api/clients';
import {
  createProductConversion,
  createProductIdentifier,
  createProductPrice,
  deleteProductConversion,
  deleteProductIdentifier,
  deleteProductPrice,
  getProduct,
} from '../api/products';
import type {
  IdentifierType,
  PriceType,
  ProductConversion,
  ProductIdentifier,
  ProductPrice,
  UnitOfMeasure,
} from '../api/products';
import { Skeleton } from '../components/Skeleton';
import { formatAed, formatFactor } from './productUi';
import styles from './Products.module.css';

const IDENTIFIER_TYPES: IdentifierType[] = [
  'MPN',
  'BARCODE',
  'SUPPLIER_CODE',
  'EAN',
  'UPC',
  'CUSTOMER_CODE',
];

const identifierSchema = z.object({
  type: z.enum(['MPN', 'BARCODE', 'SUPPLIER_CODE', 'EAN', 'UPC', 'CUSTOMER_CODE']),
  value: z.string().min(1, 'Value is required').max(255),
});

const conversionSchema = z.object({
  to_uom_id: z.string().min(1, 'Select a UOM'),
  conversion_factor: z
    .string()
    .min(1, 'Factor is required')
    .refine((value) => Number(value) > 0, 'Factor must be greater than 0'),
});

const priceSchema = z
  .object({
    price_type: z.enum(['DEFAULT_SALES', 'TIER_1', 'CUSTOMER_SPECIFIC']),
    price: z
      .string()
      .min(1, 'Price is required')
      .refine((value) => Number(value) >= 0, 'Price must be 0 or more'),
    min_quantity: z.string().optional(),
    client_id: z.string().optional(),
  })
  .superRefine((values, ctx) => {
    if (values.price_type === 'TIER_1' && !(Number(values.min_quantity) > 0)) {
      ctx.addIssue({
        code: 'custom',
        message: 'Min quantity is required for volume price',
        path: ['min_quantity'],
      });
    }
    if (values.price_type === 'CUSTOMER_SPECIFIC' && !values.client_id) {
      ctx.addIssue({
        code: 'custom',
        message: 'Client is required for customer price',
        path: ['client_id'],
      });
    }
  });

type IdentifierFormValues = z.infer<typeof identifierSchema>;
type ConversionFormValues = z.infer<typeof conversionSchema>;
type PriceFormValues = z.infer<typeof priceSchema>;

function uomCode(uoms: UnitOfMeasure[], id: string | null | undefined): string {
  if (!id) return '—';
  return uoms.find((row) => row.id === id)?.code || '—';
}

function conversionLabel(
  row: ProductConversion,
  uoms: UnitOfMeasure[],
  baseUomId: string,
): string {
  const toCode = uomCode(uoms, row.to_uom_id);
  const baseCode = uomCode(uoms, row.base_uom_id || baseUomId);
  return `1 ${toCode} = ${formatFactor(row.conversion_factor)} ${baseCode}`;
}

function priceTypeLabel(priceType: string): string {
  if (priceType === 'DEFAULT_SALES') return 'List price';
  if (priceType === 'TIER_1') return 'Volume (Tier 1)';
  if (priceType === 'CUSTOMER_SPECIFIC') return 'Customer';
  return priceType;
}

function invalidateProduct(queryClient: ReturnType<typeof useQueryClient>, productId: string) {
  queryClient.invalidateQueries({ queryKey: ['product', productId] });
  queryClient.invalidateQueries({ queryKey: ['products'] });
}

function IdentifierSection({
  productId,
  identifiers,
}: {
  productId: string;
  identifiers: ProductIdentifier[];
}) {
  const queryClient = useQueryClient();
  const { register, handleSubmit, reset, formState: { errors } } = useForm<IdentifierFormValues>({
    resolver: zodResolver(identifierSchema),
    defaultValues: { type: 'MPN', value: '' },
  });

  const createMutation = useMutation({
    mutationFn: (data: IdentifierFormValues) =>
      createProductIdentifier(productId, { type: data.type, value: data.value.trim() }),
    onSuccess: () => {
      invalidateProduct(queryClient, productId);
      reset({ type: 'MPN', value: '' });
      toast.success('Identifier added');
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteProductIdentifier(productId, id),
    onSuccess: () => {
      invalidateProduct(queryClient, productId);
      toast.success('Identifier deleted');
    },
  });

  return (
    <section className={styles.section} data-testid="identifier-section">
      <h4 className={styles.sectionTitle}>Identifiers</h4>
      <p className={styles.hint}>MPN, barcode, supplier code, EAN, UPC, or customer code.</p>
      <form className={styles.inlineForm} onSubmit={handleSubmit((values) => createMutation.mutate(values))}>
        <div className={styles.formGroup}>
          <label>Type</label>
          <select {...register('type')} data-testid="identifier-type">
            {IDENTIFIER_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.formGroup}>
          <label>Value</label>
          <input {...register('value')} data-testid="identifier-value" placeholder="DUC-4C10" />
          {errors.value && <span className={styles.errorText}>{errors.value.message}</span>}
        </div>
        <button
          type="submit"
          className={styles.primaryBtn}
          data-testid="identifier-add"
          disabled={createMutation.isPending}
        >
          Add
        </button>
      </form>
      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Type</th>
              <th>Value</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {identifiers.map((row) => (
              <tr key={row.id} data-testid={`identifier-row-${row.value}`}>
                <td>{row.type}</td>
                <td>{row.value}</td>
                <td>
                  <button
                    type="button"
                    className={`${styles.actionBtn} ${styles.delete}`}
                    onClick={() => {
                      if (window.confirm('Delete this identifier?')) deleteMutation.mutate(row.id);
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {identifiers.length === 0 && (
              <tr>
                <td colSpan={3} className={styles.emptyCell}>
                  No identifiers yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ConversionSection({
  productId,
  conversions,
  uoms,
  baseUomId,
}: {
  productId: string;
  conversions: ProductConversion[];
  uoms: UnitOfMeasure[];
  baseUomId: string;
}) {
  const queryClient = useQueryClient();
  const otherUoms = uoms.filter((row) => row.id !== baseUomId);
  const { register, handleSubmit, reset, formState: { errors } } = useForm<ConversionFormValues>({
    resolver: zodResolver(conversionSchema),
    defaultValues: { to_uom_id: '', conversion_factor: '' },
  });

  const createMutation = useMutation({
    mutationFn: (data: ConversionFormValues) =>
      createProductConversion(productId, {
        to_uom_id: data.to_uom_id,
        conversion_factor: data.conversion_factor.trim(),
      }),
    onSuccess: () => {
      invalidateProduct(queryClient, productId);
      reset({ to_uom_id: '', conversion_factor: '' });
      toast.success('Conversion added');
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteProductConversion(productId, id),
    onSuccess: () => {
      invalidateProduct(queryClient, productId);
      toast.success('Conversion deleted');
    },
  });

  return (
    <section className={styles.section} data-testid="conversion-section">
      <h4 className={styles.sectionTitle}>UOM conversions</h4>
      <p className={styles.hint}>
        1 [to UOM] = [factor] [base UOM]. Example: 1 DRUM = 500 MTR when base is MTR.
      </p>
      {otherUoms.length === 0 ? (
        <p className={styles.hint}>Add another UOM (e.g. DRUM) on the UOMs tab to create a conversion.</p>
      ) : (
        <form className={styles.inlineForm} onSubmit={handleSubmit((values) => createMutation.mutate(values))}>
          <div className={styles.formGroup}>
            <label>To UOM</label>
            <select {...register('to_uom_id')} data-testid="conversion-uom">
              <option value="">Select UOM</option>
              {otherUoms.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.code} — {row.name}
                </option>
              ))}
            </select>
            {errors.to_uom_id && <span className={styles.errorText}>{errors.to_uom_id.message}</span>}
          </div>
          <div className={styles.formGroup}>
            <label>Factor</label>
            <input {...register('conversion_factor')} data-testid="conversion-factor" placeholder="500" />
            {errors.conversion_factor && (
              <span className={styles.errorText}>{errors.conversion_factor.message}</span>
            )}
          </div>
          <button
            type="submit"
            className={styles.primaryBtn}
            data-testid="conversion-add"
            disabled={createMutation.isPending}
          >
            Add
          </button>
        </form>
      )}
      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Conversion</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {conversions.map((row) => (
              <tr key={row.id} data-testid="conversion-row">
                <td data-testid="conversion-label">{conversionLabel(row, uoms, baseUomId)}</td>
                <td>
                  <button
                    type="button"
                    className={`${styles.actionBtn} ${styles.delete}`}
                    onClick={() => {
                      if (window.confirm('Delete this conversion?')) deleteMutation.mutate(row.id);
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {conversions.length === 0 && (
              <tr>
                <td colSpan={2} className={styles.emptyCell}>
                  No conversions yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PriceSection({ productId, prices }: { productId: string; prices: ProductPrice[] }) {
  const queryClient = useQueryClient();
  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
  const { register, handleSubmit, reset, watch, formState: { errors } } = useForm<PriceFormValues>({
    resolver: zodResolver(priceSchema),
    defaultValues: { price_type: 'DEFAULT_SALES', price: '', min_quantity: '', client_id: '' },
  });
  const priceType = watch('price_type');

  const createMutation = useMutation({
    mutationFn: (data: PriceFormValues) => {
      const payload: {
        price_type: PriceType;
        currency: 'AED';
        price: string;
        min_quantity?: string;
        client_id?: string;
      } = {
        price_type: data.price_type,
        currency: 'AED',
        price: data.price.trim(),
      };
      if (data.price_type === 'TIER_1' && data.min_quantity?.trim()) {
        payload.min_quantity = data.min_quantity.trim();
      }
      if (data.price_type === 'CUSTOMER_SPECIFIC' && data.client_id) {
        payload.client_id = data.client_id;
        if (data.min_quantity?.trim()) payload.min_quantity = data.min_quantity.trim();
      }
      return createProductPrice(productId, payload);
    },
    onSuccess: () => {
      invalidateProduct(queryClient, productId);
      reset({ price_type: 'DEFAULT_SALES', price: '', min_quantity: '', client_id: '' });
      toast.success('Price added');
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteProductPrice(productId, id),
    onSuccess: () => {
      invalidateProduct(queryClient, productId);
      toast.success('Price deleted');
    },
  });

  const clientName = (clientId: string | null) => {
    if (!clientId) return '—';
    return clients?.find((row) => row.id === clientId)?.name || clientId;
  };

  return (
    <section className={styles.section} data-testid="price-section">
      <h4 className={styles.sectionTitle}>Prices (AED)</h4>
      <p className={styles.hint}>
        List price (one per product), volume break with min quantity, or customer-specific price.
      </p>
      <form className={styles.inlineForm} onSubmit={handleSubmit((values) => createMutation.mutate(values))}>
        <div className={styles.formGroup}>
          <label>Type</label>
          <select {...register('price_type')} data-testid="price-type">
            <option value="DEFAULT_SALES">List price</option>
            <option value="TIER_1">Volume (Tier 1)</option>
            <option value="CUSTOMER_SPECIFIC">Customer</option>
          </select>
        </div>
        <div className={styles.formGroup}>
          <label>Price</label>
          <input {...register('price')} data-testid="price-amount" placeholder="0.00" />
          {errors.price && <span className={styles.errorText}>{errors.price.message}</span>}
        </div>
        {priceType === 'TIER_1' || priceType === 'CUSTOMER_SPECIFIC' ? (
          <div className={styles.formGroup}>
            <label>Min quantity{priceType === 'TIER_1' ? '' : ' (optional)'}</label>
            <input {...register('min_quantity')} placeholder="10" />
            {errors.min_quantity && (
              <span className={styles.errorText}>{errors.min_quantity.message}</span>
            )}
          </div>
        ) : null}
        {priceType === 'CUSTOMER_SPECIFIC' ? (
          <div className={styles.formGroup}>
            <label>Client</label>
            <select {...register('client_id')}>
              <option value="">Select client</option>
              {clients?.map((client) => (
                <option key={client.id} value={client.id}>
                  {client.name}
                </option>
              ))}
            </select>
            {errors.client_id && <span className={styles.errorText}>{errors.client_id.message}</span>}
          </div>
        ) : null}
        <button
          type="submit"
          className={styles.primaryBtn}
          data-testid="price-add"
          disabled={createMutation.isPending}
        >
          Add
        </button>
      </form>
      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Type</th>
              <th>Price</th>
              <th>Min qty</th>
              <th>Client</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {prices.map((row) => (
              <tr key={row.id} data-testid={`price-row-${row.price_type}`}>
                <td>{priceTypeLabel(row.price_type)}</td>
                <td data-testid="price-amount-display">{formatAed(row.price)}</td>
                <td>
                  {row.min_quantity === null || row.min_quantity === undefined
                    ? '—'
                    : formatFactor(row.min_quantity)}
                </td>
                <td>{clientName(row.client_id)}</td>
                <td>
                  <button
                    type="button"
                    className={`${styles.actionBtn} ${styles.delete}`}
                    onClick={() => {
                      if (window.confirm('Delete this price?')) deleteMutation.mutate(row.id);
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {prices.length === 0 && (
              <tr>
                <td colSpan={5} className={styles.emptyCell}>
                  No prices yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function taxLabel(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return 'inherit workspace VAT';
  return `${Number(value ?? 0).toFixed(2)}%`;
}

export const ProductDetailPanel = ({
  productId,
  uoms,
  onClose,
}: {
  productId: string;
  uoms: UnitOfMeasure[];
  onClose: () => void;
}) => {
  const { data: product, isLoading } = useQuery({
    queryKey: ['product', productId],
    queryFn: () => getProduct(productId),
  });

  if (isLoading) {
    return (
      <div className={styles.detailPanel}>
        <Skeleton height="240px" />
      </div>
    );
  }

  if (!product) {
    return (
      <div className={styles.detailPanel}>
        <p className={styles.hint}>Product not found.</p>
        <button type="button" className={styles.secondaryBtn} onClick={onClose}>
          Close
        </button>
      </div>
    );
  }

  return (
    <div className={styles.detailPanel} data-testid="product-detail">
      <div className={styles.detailHeader}>
        <div>
          <h3>
            {product.internal_sku} — {product.name}
          </h3>
          <p className={styles.meta}>
            Base UOM {uomCode(uoms, product.base_uom_id)} · Tax {taxLabel(product.tax_rate)} ·
            Reorder {product.reorder_level === null || product.reorder_level === undefined
              ? '—'
              : formatFactor(product.reorder_level)}
          </p>
        </div>
        <button type="button" className={styles.secondaryBtn} onClick={onClose}>
          Close
        </button>
      </div>
      <IdentifierSection productId={productId} identifiers={product.identifiers || []} />
      <ConversionSection
        productId={productId}
        conversions={product.conversions || []}
        uoms={uoms}
        baseUomId={product.base_uom_id}
      />
      <PriceSection productId={productId} prices={product.prices || []} />
    </div>
  );
};
