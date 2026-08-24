import { useQuery } from '@tanstack/react-query';
import { getProducts, getCategories, getBrands, getUOMs } from '../api/products';
import styles from './Products.module.css';
import { Skeleton } from '../components/Skeleton';
import { Plus } from 'lucide-react';

export const Products = () => {
  const { data: products, isLoading } = useQuery({ queryKey: ['products'], queryFn: getProducts });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });
  const { data: brands } = useQuery({ queryKey: ['brands'], queryFn: getBrands });
  const { data: uoms } = useQuery({ queryKey: ['uoms'], queryFn: getUOMs });

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <h2>Products</h2>
        </div>
        <Skeleton height="400px" />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Product Master</h2>
        <button className={styles.primaryBtn} onClick={() => alert('Add Product UI coming soon')}>
          <Plus size={16} />
          Add Product
        </button>
      </div>

      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>SKU</th>
              <th>Name</th>
              <th>Category</th>
              <th>Brand</th>
              <th>Base UOM</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {products?.map((product) => {
              const category = categories?.find(c => c.id === product.category_id);
              const brand = brands?.find(b => b.id === product.brand_id);
              const uom = uoms?.find(u => u.id === product.base_uom_id);

              return (
                <tr key={product.id}>
                  <td><strong>{product.internal_sku}</strong></td>
                  <td>{product.name}</td>
                  <td>{category?.name || '-'}</td>
                  <td>{brand?.name || '-'}</td>
                  <td>{uom?.code || '-'}</td>
                  <td>{product.is_active ? 'Active' : 'Inactive'}</td>
                </tr>
              );
            })}
            {products?.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>
                  No products found. Add your first product.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
