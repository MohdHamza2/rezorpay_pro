import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getGRNs } from '../api/grn';
import { Skeleton } from '../components/Skeleton';
import { Plus, CheckCircle, PackageSearch } from 'lucide-react';
import styles from './Suppliers.module.css';

export const GoodsReceiptNotes = () => {
  const navigate = useNavigate();
  const { data: grns, isLoading } = useQuery({ queryKey: ['grns'], queryFn: getGRNs });

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <h2>Goods Receipt Notes</h2>
        </div>
        <Skeleton height="400px" />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Inbound Shipments (GRN)</h2>
        <button className={styles.primaryBtn} onClick={() => alert('Add GRN UI coming soon')}>
          <Plus size={16} />
          Receive Goods
        </button>
      </div>

      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>GRN #</th>
              <th>Status</th>
              <th>Receipt Date</th>
              <th>Supplier DN</th>
              <th>Items</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {grns?.map((grn) => (
              <tr key={grn.id}>
                <td><strong>{grn.grn_number}</strong></td>
                <td>
                  <span style={{
                    padding: '2px 8px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 'bold',
                    backgroundColor: grn.status === 'DRAFT' ? '#f3f4f6' : (grn.stock_posted ? '#dcfce7' : '#fef9c3'),
                    color: grn.status === 'DRAFT' ? '#374151' : (grn.stock_posted ? '#166534' : '#854d0e')
                  }}>
                    {grn.status}
                  </span>
                </td>
                <td>{new Date(grn.received_date).toLocaleDateString()}</td>
                <td>{grn.delivery_reference || '-'}</td>
                <td>{grn.items.length}</td>
                <td>
                  <button className={styles.actionBtn} title="Inspect Goods" onClick={() => navigate(`/grn/${grn.id}`)}>
                    <PackageSearch size={16} />
                  </button>
                  {!grn.stock_posted && (
                    <button className={styles.actionBtn} title="Post to Inventory">
                      <CheckCircle size={16} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {grns?.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>
                  No Receipts found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
