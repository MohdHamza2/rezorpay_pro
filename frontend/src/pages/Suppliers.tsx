import { useQuery } from '@tanstack/react-query';
import { getSuppliers } from '../api/suppliers';
import styles from './Suppliers.module.css';
import { Skeleton } from '../components/Skeleton';
import { Plus } from 'lucide-react';

export const Suppliers = () => {
  const { data: suppliers, isLoading } = useQuery({ queryKey: ['suppliers'], queryFn: getSuppliers });

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <h2>Suppliers</h2>
        </div>
        <Skeleton height="400px" />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Supplier Master</h2>
        <button className={styles.primaryBtn} onClick={() => alert('Add Supplier UI coming soon')}>
          <Plus size={16} />
          Add Supplier
        </button>
      </div>

      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
              <th>TRN</th>
              <th>Payment Terms</th>
              <th>Status</th>
              <th>Rating</th>
            </tr>
          </thead>
          <tbody>
            {suppliers?.map((supplier) => (
              <tr key={supplier.id}>
                <td><strong>{supplier.supplier_code}</strong></td>
                <td>{supplier.name}</td>
                <td>{supplier.trn || '-'}</td>
                <td>{supplier.payment_terms}</td>
                <td>{supplier.status}</td>
                <td>{supplier.rating || 'N/A'}</td>
              </tr>
            ))}
            {suppliers?.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>
                  No suppliers found. Add your first supplier.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
