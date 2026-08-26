import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { getSupplierInvoice, submitMatching, resolveDiscrepancy, approveInvoice } from '../api/supplier-invoices';
import { getSuppliers } from '../api/suppliers';
import styles from './Suppliers.module.css';

export const SupplierInvoiceDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [resolutionNotes, setResolutionNotes] = useState('');

  const { data: invoice, isLoading } = useQuery({
    queryKey: ['supplier-invoice', id],
    queryFn: () => getSupplierInvoice(id as string),
    enabled: !!id,
  });

  const { data: suppliers } = useQuery({
    queryKey: ['suppliers'],
    queryFn: getSuppliers,
  });

  const submitMatchingMutation = useMutation({
    mutationFn: () => submitMatching(id as string),
    onSuccess: () => {
      toast.success('3-Way Match completed');
      queryClient.invalidateQueries({ queryKey: ['supplier-invoice', id] });
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to match invoice')
  });

  const resolveMutation = useMutation({
    mutationFn: (notes: string) => resolveDiscrepancy(id as string, notes),
    onSuccess: () => {
      toast.success('Discrepancy resolved and invoice approved');
      queryClient.invalidateQueries({ queryKey: ['supplier-invoice', id] });
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to resolve')
  });

  const approveMutation = useMutation({
    mutationFn: () => approveInvoice(id as string),
    onSuccess: () => {
      toast.success('Invoice approved');
      queryClient.invalidateQueries({ queryKey: ['supplier-invoice', id] });
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to approve')
  });

  if (isLoading || !invoice) return <div style={{ padding: '2rem' }}>Loading...</div>;

  const supplier = suppliers?.find(s => s.id === invoice.supplier_id);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Supplier Invoice: {invoice.supplier_invoice_number}</h2>
        <div>
          <button className={styles.secondaryBtn} onClick={() => navigate('/supplier-invoices')} style={{ marginRight: '1rem' }}>Back</button>

          {invoice.status === 'RECEIVED' && (
            <button className={styles.primaryBtn} onClick={() => submitMatchingMutation.mutate()} disabled={submitMatchingMutation.isPending}>
              Run 3-Way Match
            </button>
          )}

          {invoice.status === 'MATCHED' && (
            <button className={styles.primaryBtn} onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending}>
              Approve for Payment
            </button>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', marginBottom: '2rem' }}>
        <div className={styles.card}>
          <h3>Invoice Details</h3>
          <p><strong>Supplier:</strong> {supplier?.name}</p>
          <p><strong>Date:</strong> {new Date(invoice.invoice_date).toLocaleDateString()}</p>
          <p><strong>Status:</strong> {invoice.status}</p>
          <p><strong>Total:</strong> {invoice.currency} {(invoice.total_amount ?? 0).toFixed(2)}</p>
        </div>

        <div className={styles.card}>
          <h3>3-Way Match Results</h3>
          <p>
            <strong>Status:</strong>{' '}
            <span style={{
              fontWeight: 'bold',
              color: invoice.three_way_match_status === 'PASSED' ? '#166534' :
                     invoice.three_way_match_status !== 'NOT_CHECKED' ? '#991b1b' : 'inherit'
            }}>
              {invoice.three_way_match_status}
            </span>
          </p>

          {invoice.status === 'DISCREPANCY' && (
            <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#fee2e2', borderRadius: '4px' }}>
              <p style={{ color: '#991b1b', fontWeight: 'bold', marginBottom: '0.5rem' }}>Discrepancy Detected</p>
              <textarea
                placeholder="Enter authorized resolution notes..."
                style={{ width: '100%', minHeight: '80px', marginBottom: '0.5rem', padding: '0.5rem' }}
                value={resolutionNotes}
                onChange={e => setResolutionNotes(e.target.value)}
              />
              <button
                className={styles.primaryBtn}
                onClick={() => resolveMutation.mutate(resolutionNotes)}
                disabled={!resolutionNotes || resolveMutation.isPending}
              >
                Authorize Override & Approve
              </button>
            </div>
          )}
          {invoice.three_way_match_notes && (
            <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: '#f3f4f6', borderRadius: '4px' }}>
              <p><strong>Resolution Notes:</strong></p>
              <p>{invoice.three_way_match_notes}</p>
            </div>
          )}
        </div>
      </div>

      <div className={styles.card}>
        <h3>Line Items</h3>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Description</th>
              <th>Qty</th>
              <th>Unit Price</th>
              <th>Total</th>
              <th>Match Result</th>
              <th>Variance</th>
            </tr>
          </thead>
          <tbody>
            {invoice.items.map((item) => (
              <tr key={item.id}>
                <td>{item.description}</td>
                <td>{item.quantity}</td>
                <td>{item.currency} {(item.unit_price ?? 0).toFixed(2)}</td>
                <td>{item.currency} {(item.total_price ?? 0).toFixed(2)}</td>
                <td>
                  <span style={{
                    color: item.match_status === 'PASSED' ? '#166534' :
                           item.match_status !== 'NOT_CHECKED' ? '#991b1b' : 'inherit',
                    fontWeight: 'bold'
                  }}>
                    {item.match_status}
                  </span>
                </td>
                <td>
                  {item.variance_quantity !== 0 && <div>Qty Diff: {item.variance_quantity}</div>}
                  {item.variance_price !== 0 && <div>Price Diff: {(item.variance_price ?? 0).toFixed(2)}</div>}
                  {item.variance_tax !== 0 && <div>Tax Diff: {(item.variance_tax ?? 0).toFixed(2)}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
