import { useQuery } from '@tanstack/react-query';
import { getRFQs } from '../api/rfq';
import { Skeleton } from '../components/Skeleton';
import { Plus, Mail, ShieldAlert } from 'lucide-react';
import styles from './Suppliers.module.css';

export const RFQMaster = () => {
  const { data: rfqs, isLoading } = useQuery({ queryKey: ['rfqs'], queryFn: getRFQs });

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <h2>RFQ Manager</h2>
        </div>
        <Skeleton height="400px" />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Requests for Quotation (RFQ)</h2>
        <button className={styles.primaryBtn} onClick={() => alert('Add RFQ UI coming soon')}>
          <Plus size={16} />
          Create RFQ
        </button>
      </div>

      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>RFQ #</th>
              <th>Type</th>
              <th>Deadline</th>
              <th>Status</th>
              <th>Items</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rfqs?.map((rfq) => (
              <tr key={rfq.id}>
                <td><strong>{rfq.rfq_number}</strong></td>
                <td>{rfq.rfq_type}</td>
                <td>{new Date(rfq.deadline).toLocaleDateString()}</td>
                <td>
                  <span style={{ 
                    padding: '2px 8px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 'bold',
                    backgroundColor: rfq.status === 'DRAFT' ? '#f3f4f6' : '#fef3c7',
                    color: rfq.status === 'DRAFT' ? '#374151' : '#92400e'
                  }}>
                    {rfq.status}
                  </span>
                </td>
                <td>{rfq.items.length}</td>
                <td>
                  <button className={styles.actionBtn} title="Invite Suppliers">
                    <Mail size={16} />
                  </button>
                  <button className={styles.actionBtn} title="Review Quotes">
                    <ShieldAlert size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {rfqs?.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>
                  No RFQs found. Convert a PR into an RFQ to begin.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
