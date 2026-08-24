import { useQuery } from '@tanstack/react-query';
import { getProcurementRequests } from '../api/procurement';
import { Skeleton } from '../components/Skeleton';
import { Plus, FileText } from 'lucide-react';
import styles from './Suppliers.module.css';

export const Procurement = () => {
  const { data: requests, isLoading } = useQuery({ queryKey: ['procurement'], queryFn: getProcurementRequests });

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <h2>Procurement Requests</h2>
        </div>
        <Skeleton height="400px" />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Internal Procurement</h2>
        <button className={styles.primaryBtn} onClick={() => alert('Add PR coming soon')}>
          <Plus size={16} />
          Create PR
        </button>
      </div>

      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>PR Number</th>
              <th>Source</th>
              <th>Destination</th>
              <th>Priority</th>
              <th>Required By</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {requests?.map((req) => (
              <tr key={req.id}>
                <td><strong>{req.request_number}</strong></td>
                <td>{req.source_type}</td>
                <td>{req.destination_type}</td>
                <td>{req.priority}</td>
                <td>{req.required_by_date}</td>
                <td>
                  <span style={{ 
                    padding: '2px 8px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 'bold',
                    backgroundColor: req.status === 'DRAFT' ? '#f3f4f6' : '#dbeafe',
                    color: req.status === 'DRAFT' ? '#374151' : '#1e40af'
                  }}>
                    {req.status}
                  </span>
                </td>
                <td>
                  <button className={styles.actionBtn} title="View Details">
                    <FileText size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {requests?.length === 0 && (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '2rem' }}>
                  No procurement requests found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
