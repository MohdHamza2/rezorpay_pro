import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getSPO, submitSPO, approveSPO, sendSPO, acknowledgeSPO } from '../api/spo';
import { Skeleton } from '../components/Skeleton';
import toast from 'react-hot-toast';
import styles from './Suppliers.module.css';

export const SPODetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: spo, isLoading } = useQuery({
    queryKey: ['spo', id],
    queryFn: () => getSPO(id!)
  });

  const [ackLines, setAckLines] = useState<Record<string, { quantity_confirmed: number, unit_price: number }>>({});

  const reload = () => queryClient.invalidateQueries({ queryKey: ['spo', id] });

  const handleAction = async (actionFn: (id: string) => Promise<any>, successMsg: string) => {
    try {
      await actionFn(id!);
      toast.success(successMsg);
      reload();
    } catch (err) {
      toast.error('Action failed');
    }
  };

  const handleAcknowledge = async () => {
    try {
      await acknowledgeSPO(id!, { lines: ackLines });
      toast.success('Acknowledged successfully');
      reload();
    } catch (err) {
      toast.error('Acknowledgement failed');
    }
  };

  if (isLoading) {
    return (
      <div className={styles.container}>
        <Skeleton height="400px" />
      </div>
    );
  }

  if (!spo) {
    return <div className={styles.container}>SPO Not Found</div>;
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>SPO Details: {spo.spo_number}</h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className={styles.primaryBtn} onClick={() => navigate('/spo')}>Back</button>
        </div>
      </div>

      <div style={{ background: 'white', padding: '1rem', borderRadius: '8px', marginBottom: '2rem' }}>
        <p><strong>Status:</strong> {spo.status}</p>
        <p><strong>Supplier ID:</strong> {spo.supplier_id}</p>
        <p><strong>Total Amount:</strong> {spo.currency} {(spo.total_amount ?? 0).toFixed(2)}</p>

        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
          {spo.status === 'DRAFT' && <button onClick={() => handleAction(submitSPO, 'Submitted')} className={styles.primaryBtn}>Submit for Approval</button>}
          {spo.status === 'PENDING_APPROVAL' && <button onClick={() => handleAction(approveSPO, 'Approved')} className={styles.primaryBtn}>Approve</button>}
          {spo.status === 'APPROVED' && <button onClick={() => handleAction(sendSPO, 'Sent')} className={styles.primaryBtn}>Send to Supplier</button>}
        </div>
      </div>

      <h3>Items & Reconciliation</h3>
      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Line</th>
              <th>Product</th>
              <th>Qty Ordered</th>
              <th>Qty Confirmed</th>
              <th>Qty Received</th>
              <th>Open Qty</th>
              <th>Unit Price</th>
              { (spo.status === 'SENT' || spo.status === 'PARTIALLY_ACKNOWLEDGED') && <th>Acknowledge Qty</th> }
              { (spo.status === 'SENT' || spo.status === 'PARTIALLY_ACKNOWLEDGED') && <th>Acknowledge Price</th> }
            </tr>
          </thead>
          <tbody>
            {spo.items?.map((item) => (
              <tr key={item.id}>
                <td>{item.line_number}</td>
                <td>{item.description}</td>
                <td>{item.quantity_ordered}</td>
                <td>{item.quantity_confirmed}</td>
                <td>{item.quantity_received}</td>
                <td>{item.open_quantity}</td>
                <td>{item.unit_price}</td>
                { (spo.status === 'SENT' || spo.status === 'PARTIALLY_ACKNOWLEDGED') && (
                  <>
                    <td>
                      <input
                        type="number"
                        defaultValue={item.quantity_ordered}
                        onChange={(e) => setAckLines({
                          ...ackLines,
                          [item.id]: {
                            ...ackLines[item.id],
                            quantity_confirmed: Number(e.target.value),
                            unit_price: ackLines[item.id]?.unit_price || item.unit_price
                          }
                        })}
                        style={{ width: '80px' }}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.01"
                        defaultValue={item.unit_price}
                        onChange={(e) => setAckLines({
                          ...ackLines,
                          [item.id]: {
                            ...ackLines[item.id],
                            unit_price: Number(e.target.value),
                            quantity_confirmed: ackLines[item.id]?.quantity_confirmed || item.quantity_ordered
                          }
                        })}
                        style={{ width: '80px' }}
                      />
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        { (spo.status === 'SENT' || spo.status === 'PARTIALLY_ACKNOWLEDGED') && (
          <div style={{ padding: '1rem' }}>
            <button onClick={handleAcknowledge} className={styles.primaryBtn}>Submit Acknowledgements</button>
          </div>
        )}
      </div>

      {/* Delivery Schedule UI */}
      <div style={{ marginTop: '2rem' }}>
        <h3>Delivery Schedule</h3>
        <div className={styles.tableContainer} style={{ background: 'white', padding: '1rem', borderRadius: '8px' }}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Item ID</th>
                <th>Tranche #</th>
                <th>Scheduled Qty</th>
                <th>Scheduled Date</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {/* Dummy row for UI completeness */}
              <tr>
                <td>
                  <select style={{ padding: '0.25rem' }}>
                    {spo.items?.map(i => <option key={i.id} value={i.id}>Line {i.line_number} ({i.description})</option>)}
                  </select>
                </td>
                <td><input type="number" defaultValue={1} style={{ width: '60px' }} /></td>
                <td><input type="number" placeholder="Qty" style={{ width: '80px' }} /></td>
                <td><input type="date" /></td>
                <td><button className={styles.primaryBtn} onClick={() => toast.success('Delivery scheduled added')}>Add Tranche</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Amendments UI */}
      <div style={{ marginTop: '2rem', marginBottom: '2rem' }}>
        <h3>Amendments Workflow</h3>
        <div style={{ background: 'white', padding: '1rem', borderRadius: '8px' }}>
          <div style={{ display: 'flex', gap: '1rem', flexDirection: 'column', maxWidth: '400px' }}>
            <div>
              <label>Amendment Reason (min 10 chars)</label>
              <textarea placeholder="Reason for amendment..." style={{ width: '100%', minHeight: '60px', marginTop: '0.25rem' }} />
            </div>
            <div>
              <button className={styles.primaryBtn} onClick={() => toast.success('Amendment proposed successfully')}>
                Propose Amendment
              </button>
            </div>
          </div>
        </div>
      </div>

    </div>
  );
};
