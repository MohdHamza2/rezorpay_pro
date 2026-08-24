import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getSupplierInvoices } from '../api/supplier-invoices';
import { getSuppliers } from '../api/suppliers';
import styles from './Suppliers.module.css';

export const SupplierInvoices = () => {
  const navigate = useNavigate();

  const { data: invoices, isLoading } = useQuery({
    queryKey: ['supplier-invoices'],
    queryFn: getSupplierInvoices,
  });

  const { data: suppliers } = useQuery({
    queryKey: ['suppliers'],
    queryFn: getSuppliers,
  });

  if (isLoading) return <div style={{ padding: '2rem' }}>Loading Supplier Invoices...</div>;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Supplier Invoices (AP)</h2>
        <button className={styles.primaryBtn} onClick={() => navigate('/supplier-invoices/new')}>
          + New Supplier Invoice
        </button>
      </div>

      <div className={styles.card}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Invoice Number</th>
              <th>Supplier</th>
              <th>Date</th>
              <th>Total Amount</th>
              <th>Status</th>
              <th>Match Result</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {invoices?.map((invoice) => {
              const supplier = suppliers?.find((s) => s.id === invoice.supplier_id);
              return (
                <tr key={invoice.id}>
                  <td><strong>{invoice.supplier_invoice_number}</strong></td>
                  <td>{supplier?.name || invoice.supplier_id}</td>
                  <td>{new Date(invoice.invoice_date).toLocaleDateString()}</td>
                  <td>{invoice.currency} {invoice.total_amount.toFixed(2)}</td>
                  <td>
                    <span className={`${styles.badge} ${styles['status' + invoice.status] || ''}`}>
                      {invoice.status}
                    </span>
                  </td>
                  <td>
                    {invoice.three_way_match_status !== 'NOT_CHECKED' && (
                      <span className={styles.badge} style={{ 
                        backgroundColor: invoice.three_way_match_status === 'PASSED' ? '#dcfce7' : '#fee2e2',
                        color: invoice.three_way_match_status === 'PASSED' ? '#166534' : '#991b1b'
                      }}>
                        {invoice.three_way_match_status}
                      </span>
                    )}
                  </td>
                  <td>
                    <button 
                      className={styles.secondaryBtn} 
                      onClick={() => navigate(`/supplier-invoices/${invoice.id}`)}
                    >
                      View
                    </button>
                  </td>
                </tr>
              );
            })}
            {!invoices?.length && (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: '#6b7280' }}>
                  No Supplier Invoices found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
