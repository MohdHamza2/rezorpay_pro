import { useQuery } from '@tanstack/react-query';
import { getWarehouses } from '../api/inventory';
import { Skeleton } from '../components/Skeleton';
import { Plus, Package } from 'lucide-react';
import styles from './Suppliers.module.css'; // Reusing layout

export const Inventory = () => {
  const { data: warehouses, isLoading } = useQuery({ queryKey: ['warehouses'], queryFn: getWarehouses });

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <h2>Inventory Management</h2>
        </div>
        <Skeleton height="400px" />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Warehouses & Locations</h2>
        <button className={styles.primaryBtn} onClick={() => alert('Add Warehouse coming soon')}>
          <Plus size={16} />
          Add Warehouse
        </button>
      </div>

      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
              <th>Location</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {warehouses?.map((wh) => (
              <tr key={wh.id}>
                <td><strong>{wh.code}</strong></td>
                <td>{wh.name}</td>
                <td>{wh.location || '-'}</td>
                <td>{wh.is_active ? 'Active' : 'Inactive'}</td>
                <td>
                  <button className={styles.primaryBtn} style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>
                    <Package size={12} style={{ marginRight: 4 }} />
                    View Stock
                  </button>
                </td>
              </tr>
            ))}
            {warehouses?.length === 0 && (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: '2rem' }}>
                  No warehouses found. Set up your first location.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
