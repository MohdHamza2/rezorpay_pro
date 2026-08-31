import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import toast from 'react-hot-toast';
import { Edit2, Plus, Trash2 } from 'lucide-react';
import {
  PRODUCT_PAGE_SIZE,
  createProduct,
  deleteProduct,
  getBrands,
  getCategories,
  getProducts,
  getUOMs,
  updateProduct,
} from '../api/products';
import type { Brand, Category, Product, ProductWrite, UnitOfMeasure } from '../api/products';
import { BrandsTab, CategoriesTab, UomsTab } from './ProductCatalogTabs';
import { ProductDetailPanel } from './ProductDetailPanel';
import {
  PaginationBar,
  ProductModal,
  TableSkeleton,
  confirmSoftDelete,
  optionalAmount,
  optionalId,
} from './productUi';
import styles from './Products.module.css';

type Tab = 'products' | 'categories' | 'brands' | 'uoms';

const TABS: { id: Tab; label: string }[] = [
  { id: 'products', label: 'Products' },
  { id: 'categories', label: 'Categories' },
  { id: 'brands', label: 'Brands' },
  { id: 'uoms', label: 'UOMs' },
];

const productSchema = z.object({
  internal_sku: z.string().min(1, 'SKU is required').max(100),
  name: z.string().min(1, 'Name is required').max(255),
  base_uom_id: z.string().min(1, 'Base UOM is required'),
  description: z.string().optional(),
  category_id: z.string().optional(),
  brand_id: z.string().optional(),
  is_active: z.boolean(),
  tax_rate: z
    .string()
    .optional()
    .refine((value) => !value || value.trim() === '' || Number(value) >= 0, 'Tax rate must be 0–100')
    .refine((value) => !value || value.trim() === '' || Number(value) <= 100, 'Tax rate must be 0–100'),
  reorder_level: z
    .string()
    .optional()
    .refine((value) => !value || value.trim() === '' || Number(value) >= 0, 'Reorder level must be 0 or more'),
});

type ProductFormValues = z.infer<typeof productSchema>;

function lookupName(rows: { id: string; name: string }[] | undefined, id: string | null): string {
  if (!id) return '—';
  return rows?.find((row) => row.id === id)?.name || '—';
}

function lookupCode(rows: UnitOfMeasure[] | undefined, id: string | null): string {
  if (!id) return '—';
  return rows?.find((row) => row.id === id)?.code || '—';
}

function buildProductCreate(values: ProductFormValues): ProductWrite {
  const payload: ProductWrite = {
    internal_sku: values.internal_sku.trim(),
    name: values.name.trim(),
    base_uom_id: values.base_uom_id,
    is_active: values.is_active,
  };
  if (values.description?.trim()) payload.description = values.description.trim();
  if (values.category_id) payload.category_id = values.category_id;
  if (values.brand_id) payload.brand_id = values.brand_id;
  const taxRate = optionalAmount(values.tax_rate);
  if (taxRate) payload.tax_rate = taxRate;
  const reorder = optionalAmount(values.reorder_level);
  if (reorder) payload.reorder_level = reorder;
  return payload;
}

function buildProductUpdate(values: ProductFormValues): ProductWrite {
  return {
    internal_sku: values.internal_sku.trim(),
    name: values.name.trim(),
    base_uom_id: values.base_uom_id,
    is_active: values.is_active,
    description: values.description?.trim() || null,
    category_id: optionalId(values.category_id),
    brand_id: optionalId(values.brand_id),
    tax_rate: optionalAmount(values.tax_rate),
    reorder_level: optionalAmount(values.reorder_level),
  };
}

function ProductFormModal({
  editing,
  categories,
  brands,
  uoms,
  onClose,
}: {
  editing: Product | null;
  categories: Category[];
  brands: Brand[];
  uoms: UnitOfMeasure[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { register, handleSubmit, formState: { errors } } = useForm<ProductFormValues>({
    resolver: zodResolver(productSchema),
    defaultValues: {
      internal_sku: editing?.internal_sku ?? '',
      name: editing?.name ?? '',
      base_uom_id: editing?.base_uom_id ?? '',
      description: editing?.description ?? '',
      category_id: editing?.category_id ?? '',
      brand_id: editing?.brand_id ?? '',
      is_active: editing?.is_active ?? true,
      tax_rate: editing?.tax_rate === null || editing?.tax_rate === undefined ? '' : String(editing.tax_rate),
      reorder_level:
        editing?.reorder_level === null || editing?.reorder_level === undefined
          ? ''
          : String(editing.reorder_level),
    },
  });

  const createMutation = useMutation({
    mutationFn: createProduct,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      onClose();
      toast.success('Product created');
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ProductWrite }) => updateProduct(id, data),
    onSuccess: (_product, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['product', variables.id] });
      onClose();
      toast.success('Product updated');
    },
  });

  const onSubmit = (values: ProductFormValues) => {
    if (editing) {
      updateMutation.mutate({ id: editing.id, data: buildProductUpdate(values) });
      return;
    }
    createMutation.mutate(buildProductCreate(values));
  };

  return (
    <ProductModal title={editing ? 'Edit Product' : 'Add Product'} onClose={onClose} wide>
      {uoms.length === 0 && (
        <p className={styles.hint}>Create a unit of measure on the UOMs tab before adding a product.</p>
      )}
      <form onSubmit={handleSubmit(onSubmit)}>
        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label>Internal SKU</label>
            <input
              {...register('internal_sku')}
              data-testid="product-sku-input"
              placeholder="ELE-CBL-4C10"
            />
            {errors.internal_sku && (
              <span className={styles.errorText}>{errors.internal_sku.message}</span>
            )}
          </div>
          <div className={styles.formGroup}>
            <label>Name</label>
            <input
              {...register('name')}
              data-testid="product-name-input"
              placeholder="4-core 10mm² XLPE"
            />
            {errors.name && <span className={styles.errorText}>{errors.name.message}</span>}
          </div>
        </div>
        <div className={styles.formGroup}>
          <label>Description</label>
          <textarea {...register('description')} />
        </div>
        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label>Base UOM</label>
            <select {...register('base_uom_id')} data-testid="product-uom-select">
              <option value="">Select UOM</option>
              {uoms.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.code} — {row.name}
                </option>
              ))}
            </select>
            {errors.base_uom_id && (
              <span className={styles.errorText}>{errors.base_uom_id.message}</span>
            )}
          </div>
          <div className={styles.formGroup}>
            <label>Category</label>
            <select {...register('category_id')} data-testid="product-category-select">
              <option value="">None</option>
              {categories.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label>Brand</label>
            <select {...register('brand_id')} data-testid="product-brand-select">
              <option value="">None</option>
              {brands.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.formGroup}>
            <label>Tax rate % (optional)</label>
            <input {...register('tax_rate')} placeholder="Leave blank to inherit 5% VAT" />
            {errors.tax_rate && <span className={styles.errorText}>{errors.tax_rate.message}</span>}
          </div>
        </div>
        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label>Reorder level</label>
            <input {...register('reorder_level')} />
            {errors.reorder_level && (
              <span className={styles.errorText}>{errors.reorder_level.message}</span>
            )}
          </div>
          <div className={styles.formGroup}>
            <label className={styles.checkboxRow}>
              <input type="checkbox" {...register('is_active')} />
              Active
            </label>
          </div>
        </div>
        <div className={styles.modalActions}>
          <button type="button" className={styles.secondaryBtn} onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            className={styles.primaryBtn}
            data-testid="product-form-submit"
            disabled={createMutation.isPending || updateMutation.isPending || uoms.length === 0}
          >
            {editing ? 'Update' : 'Create'}
          </button>
        </div>
      </form>
    </ProductModal>
  );
}

function ProductsTab() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['products', { page }],
    queryFn: () => getProducts({ page, per_page: PRODUCT_PAGE_SIZE }),
  });
  const { data: categoryResult } = useQuery({
    queryKey: ['categories', 'lookup'],
    queryFn: () => getCategories({ page: 1, per_page: PRODUCT_PAGE_SIZE }),
  });
  const { data: brandResult } = useQuery({
    queryKey: ['brands', 'lookup'],
    queryFn: () => getBrands({ page: 1, per_page: PRODUCT_PAGE_SIZE }),
  });
  const { data: uomResult } = useQuery({
    queryKey: ['uoms', 'lookup'],
    queryFn: () => getUOMs({ page: 1, per_page: PRODUCT_PAGE_SIZE }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteProduct,
    onSuccess: (_void, id) => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['product', id] });
      if (selectedId === id) setSelectedId(null);
      toast.success('Product deleted');
    },
  });

  const products = data?.items ?? [];
  const categories = categoryResult?.items ?? [];
  const brands = brandResult?.items ?? [];
  const uoms = uomResult?.items ?? [];

  const openModal = (product?: Product) => {
    setEditing(product ?? null);
    setIsModalOpen(true);
  };

  return (
    <div>
      <div className={styles.toolbar}>
        <button
          className={styles.primaryBtn}
          onClick={() => openModal()}
          type="button"
          data-testid="add-product"
        >
          <Plus size={16} />
          Add Product
        </button>
      </div>
      <div className={styles.tableContainer}>
        {isLoading ? (
          <TableSkeleton />
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>SKU</th>
                <th>Name</th>
                <th>Category</th>
                <th>Brand</th>
                <th>Base UOM</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {products.map((product) => (
                <tr
                  key={product.id}
                  data-testid={`product-row-${product.internal_sku}`}
                  data-product-id={product.id}
                  className={`${styles.clickableRow} ${selectedId === product.id ? styles.selectedRow : ''}`}
                  onClick={() => setSelectedId(product.id)}
                >
                  <td>
                    <strong>{product.internal_sku}</strong>
                  </td>
                  <td>{product.name}</td>
                  <td>{lookupName(categories, product.category_id)}</td>
                  <td>{lookupName(brands, product.brand_id)}</td>
                  <td>{lookupCode(uoms, product.base_uom_id)}</td>
                  <td>
                    <span className={product.is_active ? styles.badgeActive : styles.badgeInactive}>
                      {product.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>
                    <button
                      className={styles.actionBtn}
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        openModal(product);
                      }}
                    >
                      <Edit2 size={16} />
                    </button>
                    <button
                      className={`${styles.actionBtn} ${styles.delete}`}
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        if (confirmSoftDelete('product')) deleteMutation.mutate(product.id);
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {products.length === 0 && (
                <tr>
                  <td colSpan={7} className={styles.emptyCell}>
                    No products found. Add a category, brand, and UOM, then create your first product.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        <PaginationBar pagination={data?.pagination} onPage={setPage} />
      </div>
      {selectedId && (
        <ProductDetailPanel productId={selectedId} uoms={uoms} onClose={() => setSelectedId(null)} />
      )}
      {isModalOpen && (
        <ProductFormModal
          editing={editing}
          categories={categories}
          brands={brands}
          uoms={uoms}
          onClose={() => {
            setIsModalOpen(false);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

export const Products = () => {
  const [tab, setTab] = useState<Tab>('products');

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Product Master</h2>
      </div>
      <div className={styles.tabs} role="tablist">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            data-testid={`tab-${item.id}`}
            aria-selected={tab === item.id}
            className={tab === item.id ? `${styles.tab} ${styles.tabActive}` : styles.tab}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {tab === 'products' && <ProductsTab />}
      {tab === 'categories' && <CategoriesTab />}
      {tab === 'brands' && <BrandsTab />}
      {tab === 'uoms' && <UomsTab />}
    </div>
  );
};
