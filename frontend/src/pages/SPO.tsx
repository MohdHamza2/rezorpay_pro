import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getSPOs } from '../api/spo';
import { Skeleton } from '../components/Skeleton';
import { Plus, Printer, Truck, Eye } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import styles from './Suppliers.module.css';

export const PurchaseOrders = () => {
  const navigate = useNavigate();
  // We assume workspace_id might be needed, omitting for now or replace with real auth context if available
  const { data: spos, isLoading } = useQuery({ queryKey: ['spos'], queryFn: () => getSPOs() });

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <h2>Purchase Orders</h2>
        </div>
        <Skeleton height="400px" />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Supplier Purchase Orders (SPO)</h2>
        <button className={styles.primaryBtn} onClick={() => navigate('/spo/new')}>
          <Plus size={16} />
          Create SPO
        </button>
      </div>

      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>PO #</th>
              <th>Status</th>
              <th>Delivery Date</th>
              <th>Amount</th>
              <th>Items</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {spos?.map((spo) => (
              <tr key={spo.id}>
                <td><strong>{spo.spo_number}</strong></td>
                <td>
                  <span style={{ 
                    padding: '2px 8px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 'bold',
                    backgroundColor: spo.status === 'DRAFT' ? '#f3f4f6' : '#dbeafe',
                    color: spo.status === 'DRAFT' ? '#374151' : '#1e40af'
                  }}>
                    {spo.status}
                  </span>
                </td>
                <td>{spo.expected_delivery_date || '-'}</td>
                <td>{spo.currency} {spo.total_amount?.toFixed(2)}</td>
                <td>{spo.items?.length || 0}</td>
                <td>
                  <button className={styles.actionBtn} title="View Details" onClick={() => navigate(`/spo/${spo.id}`)}>
                    <Eye size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {(!spos || spos.length === 0) && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>
                  No Purchase Orders found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
