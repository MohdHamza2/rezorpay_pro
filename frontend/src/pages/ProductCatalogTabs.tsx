import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import toast from 'react-hot-toast';
import { Edit2, Plus, Trash2 } from 'lucide-react';
import {
  PRODUCT_PAGE_SIZE,
  createBrand,
  createCategory,
  createUOM,
  deleteBrand,
  deleteCategory,
  deleteUOM,
  getBrands,
  getCategories,
  getUOMs,
  updateBrand,
  updateCategory,
  updateUOM,
} from '../api/products';
import type { Brand, Category, UnitOfMeasure } from '../api/products';
import {
  PaginationBar,
  ProductModal,
  TableSkeleton,
  confirmSoftDelete,
  optionalId,
} from './productUi';
import styles from './Products.module.css';

const categorySchema = z.object({
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string().optional(),
  parent_id: z.string().optional(),
});

const brandSchema = z.object({
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string().optional(),
});

const uomSchema = z.object({
  code: z.string().min(1, 'Code is required').max(50),
  name: z.string().min(1, 'Name is required').max(255),
});

type CategoryFormValues = z.infer<typeof categorySchema>;
type BrandFormValues = z.infer<typeof brandSchema>;
type UomFormValues = z.infer<typeof uomSchema>;

function parentName(categories: Category[], parentId: string | null): string {
  if (!parentId) return '—';
  return categories.find((row) => row.id === parentId)?.name || '—';
}

export const CategoriesTab = () => {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editing, setEditing] = useState<Category | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['categories', { page }],
    queryFn: () => getCategories({ page, per_page: PRODUCT_PAGE_SIZE }),
  });
  const { data: lookup } = useQuery({
    queryKey: ['categories', 'lookup'],
    queryFn: () => getCategories({ page: 1, per_page: PRODUCT_PAGE_SIZE }),
  });

  const { register, handleSubmit, reset, formState: { errors } } = useForm<CategoryFormValues>({
    resolver: zodResolver(categorySchema),
  });

  const createMutation = useMutation({
    mutationFn: createCategory,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      closeModal();
      toast.success('Category created');
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: CategoryFormValues }) =>
      updateCategory(id, {
        name: data.name.trim(),
        description: data.description?.trim() || null,
        parent_id: optionalId(data.parent_id),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      closeModal();
      toast.success('Category updated');
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteCategory,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      toast.success('Category deleted');
    },
  });

  const openModal = (row?: Category) => {
    setEditing(row ?? null);
    reset({
      name: row?.name ?? '',
      description: row?.description ?? '',
      parent_id: row?.parent_id ?? '',
    });
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditing(null);
    reset();
  };

  const onSubmit = (values: CategoryFormValues) => {
    if (editing) {
      updateMutation.mutate({ id: editing.id, data: values });
      return;
    }
    createMutation.mutate({
      name: values.name.trim(),
      ...(values.description?.trim() ? { description: values.description.trim() } : {}),
      ...(values.parent_id ? { parent_id: values.parent_id } : {}),
    });
  };

  const categories = data?.items ?? [];
  const allCategories = lookup?.items ?? categories;
  const parentOptions = allCategories.filter((row) => row.id !== editing?.id);

  return (
    <div>
      <div className={styles.toolbar}>
        <button
          className={styles.primaryBtn}
          onClick={() => openModal()}
          type="button"
          data-testid="add-category"
        >
          <Plus size={16} />
          Add Category
        </button>
      </div>
      <div className={styles.tableContainer}>
        {isLoading ? (
          <TableSkeleton />
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Parent</th>
                <th>Description</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((row) => (
                <tr key={row.id} data-testid={`category-row-${row.name}`}>
                  <td>{row.name}</td>
                  <td>{parentName(allCategories, row.parent_id)}</td>
                  <td>{row.description || '—'}</td>
                  <td>
                    <button className={styles.actionBtn} onClick={() => openModal(row)} type="button">
                      <Edit2 size={16} />
                    </button>
                    <button
                      className={`${styles.actionBtn} ${styles.delete}`}
                      type="button"
                      onClick={() => {
                        if (confirmSoftDelete('category')) deleteMutation.mutate(row.id);
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {categories.length === 0 && (
                <tr>
                  <td colSpan={4} className={styles.emptyCell}>
                    No categories yet. Add a category first, then brands and UOMs.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        <PaginationBar pagination={data?.pagination} onPage={setPage} />
      </div>

      {isModalOpen && (
        <ProductModal title={editing ? 'Edit Category' : 'Add Category'} onClose={closeModal}>
          <form onSubmit={handleSubmit(onSubmit)}>
            <div className={styles.formGroup}>
              <label>Name</label>
              <input {...register('name')} data-testid="category-name-input" />
              {errors.name && <span className={styles.errorText}>{errors.name.message}</span>}
            </div>
            <div className={styles.formGroup}>
              <label>Parent (optional)</label>
              <select {...register('parent_id')}>
                <option value="">None</option>
                {parentOptions.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </select>
            </div>
            <div className={styles.formGroup}>
              <label>Description</label>
              <textarea {...register('description')} />
            </div>
            <div className={styles.modalActions}>
              <button type="button" className={styles.secondaryBtn} onClick={closeModal}>
                Cancel
              </button>
              <button
                type="submit"
                className={styles.primaryBtn}
                data-testid="category-form-submit"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                {editing ? 'Update' : 'Create'}
              </button>
            </div>
          </form>
        </ProductModal>
      )}
    </div>
  );
};

export const BrandsTab = () => {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editing, setEditing] = useState<Brand | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['brands', { page }],
    queryFn: () => getBrands({ page, per_page: PRODUCT_PAGE_SIZE }),
  });

  const { register, handleSubmit, reset, formState: { errors } } = useForm<BrandFormValues>({
    resolver: zodResolver(brandSchema),
  });

  const createMutation = useMutation({
    mutationFn: createBrand,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brands'] });
      closeModal();
      toast.success('Brand created');
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: BrandFormValues }) =>
      updateBrand(id, {
        name: data.name.trim(),
        description: data.description?.trim() || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brands'] });
      closeModal();
      toast.success('Brand updated');
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteBrand,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brands'] });
      toast.success('Brand deleted');
    },
  });

  const openModal = (row?: Brand) => {
    setEditing(row ?? null);
    reset({ name: row?.name ?? '', description: row?.description ?? '' });
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditing(null);
    reset();
  };

  const onSubmit = (values: BrandFormValues) => {
    if (editing) {
      updateMutation.mutate({ id: editing.id, data: values });
      return;
    }
    createMutation.mutate({
      name: values.name.trim(),
      ...(values.description?.trim() ? { description: values.description.trim() } : {}),
    });
  };

  const brands = data?.items ?? [];

  return (
    <div>
      <div className={styles.toolbar}>
        <button
          className={styles.primaryBtn}
          onClick={() => openModal()}
          type="button"
          data-testid="add-brand"
        >
          <Plus size={16} />
          Add Brand
        </button>
      </div>
      <div className={styles.tableContainer}>
        {isLoading ? (
          <TableSkeleton />
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {brands.map((row) => (
                <tr key={row.id} data-testid={`brand-row-${row.name}`}>
                  <td>{row.name}</td>
                  <td>{row.description || '—'}</td>
                  <td>
                    <button className={styles.actionBtn} onClick={() => openModal(row)} type="button">
                      <Edit2 size={16} />
                    </button>
                    <button
                      className={`${styles.actionBtn} ${styles.delete}`}
                      type="button"
                      onClick={() => {
                        if (confirmSoftDelete('brand')) deleteMutation.mutate(row.id);
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {brands.length === 0 && (
                <tr>
                  <td colSpan={3} className={styles.emptyCell}>
                    No brands yet. Add a brand (optional) before creating products.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        <PaginationBar pagination={data?.pagination} onPage={setPage} />
      </div>

      {isModalOpen && (
        <ProductModal title={editing ? 'Edit Brand' : 'Add Brand'} onClose={closeModal}>
          <form onSubmit={handleSubmit(onSubmit)}>
            <div className={styles.formGroup}>
              <label>Name</label>
              <input {...register('name')} data-testid="brand-name-input" />
              {errors.name && <span className={styles.errorText}>{errors.name.message}</span>}
            </div>
            <div className={styles.formGroup}>
              <label>Description</label>
              <textarea {...register('description')} />
            </div>
            <div className={styles.modalActions}>
              <button type="button" className={styles.secondaryBtn} onClick={closeModal}>
                Cancel
              </button>
              <button
                type="submit"
                className={styles.primaryBtn}
                data-testid="brand-form-submit"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                {editing ? 'Update' : 'Create'}
              </button>
            </div>
          </form>
        </ProductModal>
      )}
    </div>
  );
};

export const UomsTab = () => {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editing, setEditing] = useState<UnitOfMeasure | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['uoms', { page }],
    queryFn: () => getUOMs({ page, per_page: PRODUCT_PAGE_SIZE }),
  });

  const { register, handleSubmit, reset, formState: { errors } } = useForm<UomFormValues>({
    resolver: zodResolver(uomSchema),
  });

  const createMutation = useMutation({
    mutationFn: createUOM,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['uoms'] });
      closeModal();
      toast.success('Unit of measure created');
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: UomFormValues }) =>
      updateUOM(id, { code: data.code.trim(), name: data.name.trim() }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['uoms'] });
      closeModal();
      toast.success('Unit of measure updated');
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteUOM,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['uoms'] });
      toast.success('Unit of measure deleted');
    },
  });

  const openModal = (row?: UnitOfMeasure) => {
    setEditing(row ?? null);
    reset({ code: row?.code ?? '', name: row?.name ?? '' });
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditing(null);
    reset();
  };

  const onSubmit = (values: UomFormValues) => {
    const payload = { code: values.code.trim(), name: values.name.trim() };
    if (editing) {
      updateMutation.mutate({ id: editing.id, data: payload });
      return;
    }
    createMutation.mutate(payload);
  };

  const uoms = data?.items ?? [];

  return (
    <div>
      <div className={styles.toolbar}>
        <button
          className={styles.primaryBtn}
          onClick={() => openModal()}
          type="button"
          data-testid="add-uom"
        >
          <Plus size={16} />
          Add UOM
        </button>
      </div>
      <div className={styles.tableContainer}>
        {isLoading ? (
          <TableSkeleton />
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Code</th>
                <th>Name</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {uoms.map((row) => (
                <tr key={row.id} data-testid={`uom-row-${row.code}`}>
                  <td>
                    <strong>{row.code}</strong>
                  </td>
                  <td>{row.name}</td>
                  <td>
                    <button className={styles.actionBtn} onClick={() => openModal(row)} type="button">
                      <Edit2 size={16} />
                    </button>
                    <button
                      className={`${styles.actionBtn} ${styles.delete}`}
                      type="button"
                      onClick={() => {
                        if (confirmSoftDelete('unit of measure')) deleteMutation.mutate(row.id);
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {uoms.length === 0 && (
                <tr>
                  <td colSpan={3} className={styles.emptyCell}>
                    No units of measure yet. Add one (e.g. MTR, PCS, DRUM) before creating a product.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        <PaginationBar pagination={data?.pagination} onPage={setPage} />
      </div>

      {isModalOpen && (
        <ProductModal title={editing ? 'Edit UOM' : 'Add UOM'} onClose={closeModal}>
          <form onSubmit={handleSubmit(onSubmit)}>
            <div className={styles.formGroup}>
              <label>Code</label>
              <input {...register('code')} data-testid="uom-code-input" placeholder="MTR" />
              {errors.code && <span className={styles.errorText}>{errors.code.message}</span>}
            </div>
            <div className={styles.formGroup}>
              <label>Name</label>
              <input {...register('name')} data-testid="uom-name-input" placeholder="Metre" />
              {errors.name && <span className={styles.errorText}>{errors.name.message}</span>}
            </div>
            <div className={styles.modalActions}>
              <button type="button" className={styles.secondaryBtn} onClick={closeModal}>
                Cancel
              </button>
              <button
                type="submit"
                className={styles.primaryBtn}
                data-testid="uom-form-submit"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                {editing ? 'Update' : 'Create'}
              </button>
            </div>
          </form>
        </ProductModal>
      )}
    </div>
  );
};
