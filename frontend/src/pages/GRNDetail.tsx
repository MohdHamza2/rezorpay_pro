import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, Controller } from 'react-hook-form';
import toast from 'react-hot-toast';
import { getGRNReconciliation, startReceiving, stageForInspection, recordDisposition, addGRNItem } from '../api/grn';
import type { GRNDispositionRequest, GRNItemCreate } from '../api/grn';
import { getSPO } from '../api/spo';
import styles from './Suppliers.module.css';

interface DispositionFormData {
  [itemId: string]: {
    quantity_accepted: number;
    quantity_damaged: number;
    quantity_rejected: number;
    damage_reason: string;
    rejection_reason: string;
  }
}

export const GRNDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: grn, isLoading } = useQuery({
    queryKey: ['grn', id],
    queryFn: () => getGRNReconciliation(id as string),
    enabled: !!id,
  });

  const { data: spo } = useQuery({
    queryKey: ['spo', grn?.spo_id],
    queryFn: () => getSPO(grn?.spo_id as string),
    enabled: !!grn?.spo_id,
  });

  const { control, handleSubmit } = useForm<DispositionFormData>();
  const [selectedSpoItemId, setSelectedSpoItemId] = useState<string>('');
  const [qtyReceivedInput, setQtyReceivedInput] = useState<number>(0);

  const startReceivingMutation = useMutation({
    mutationFn: startReceiving,
    onSuccess: () => {
      toast.success('Started receiving goods');
      queryClient.invalidateQueries({ queryKey: ['grn', id] });
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to start receiving')
  });

  const stageForInspectionMutation = useMutation({
    mutationFn: stageForInspection,
    onSuccess: () => {
      toast.success('Staged for inspection');
      queryClient.invalidateQueries({ queryKey: ['grn', id] });
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to stage for inspection')
  });

  const recordDispositionMutation = useMutation({
    mutationFn: ({ itemId, data }: { itemId: string, data: GRNDispositionRequest }) => recordDisposition(id as string, itemId, data),
    onSuccess: () => {
      toast.success('Disposition recorded successfully');
      queryClient.invalidateQueries({ queryKey: ['grn', id] });
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to record disposition')
  });

  const addItemMutation = useMutation({
    mutationFn: (data: GRNItemCreate) => addGRNItem(id as string, data),
    onSuccess: () => {
      toast.success('Item added');
      setSelectedSpoItemId('');
      setQtyReceivedInput(0);
      queryClient.invalidateQueries({ queryKey: ['grn', id] });
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Failed to add item')
  });

  if (isLoading || !grn) return <div style={{ padding: '2rem' }}>Loading GRN...</div>;

  const handleDispositionSubmit = (itemId: string, data: any) => {
    const itemData = data[itemId];
    if (!itemData) return;

    const qty_accepted = Number(itemData.quantity_accepted || 0);
    const qty_damaged = Number(itemData.quantity_damaged || 0);
    const qty_rejected = Number(itemData.quantity_rejected || 0);

    const grnItem = grn.items.find(i => i.id === itemId);
    if (!grnItem) return;

    if (qty_accepted + qty_damaged + qty_rejected !== Number(grnItem.quantity_received)) {
      toast.error(`Quantities must sum up to total quantity received (${grnItem.quantity_received}).`);
      return;
    }

    if (qty_damaged > 0 && (!itemData.damage_reason || itemData.damage_reason.length < 10)) {
      toast.error('Damage reason is required (min 10 chars) if damaged > 0');
      return;
    }

    if (qty_rejected > 0 && (!itemData.rejection_reason || itemData.rejection_reason.length < 10)) {
      toast.error('Rejection reason is required (min 10 chars) if rejected > 0');
      return;
    }

    recordDispositionMutation.mutate({
      itemId,
      data: {
        quantity_accepted: qty_accepted,
        quantity_damaged: qty_damaged,
        quantity_rejected: qty_rejected,
        damage_reason: itemData.damage_reason,
        rejection_reason: itemData.rejection_reason
      }
    });
  };

  const handleAddItem = () => {
    if (!selectedSpoItemId || qtyReceivedInput <= 0) {
      toast.error('Select an SPO item and enter quantity received > 0');
      return;
    }
    const spoItem = spo?.items.find((i: any) => i.id === selectedSpoItemId);
    if (!spoItem) return;

    addItemMutation.mutate({
      spo_item_id: spoItem.id,
      product_id: spoItem.product_id,
      internal_sku: spoItem.internal_sku ?? '',
      description: spoItem.description,
      uom_id: spoItem.uom_id,
      quantity_received: qtyReceivedInput
    });
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>GRN Reconciliation: {grn.grn_number}</h2>
        <div>
          <button className={styles.secondaryBtn} onClick={() => navigate('/grn')} style={{ marginRight: '1rem' }}>Back</button>
          {grn.status === 'DRAFT' && (
            <button className={styles.primaryBtn} onClick={() => startReceivingMutation.mutate(grn.id)} disabled={startReceivingMutation.isPending}>
              Start Receiving
            </button>
          )}
          {grn.status === 'RECEIVING' && (
            <button className={styles.primaryBtn} onClick={() => stageForInspectionMutation.mutate(grn.id)} disabled={stageForInspectionMutation.isPending || grn.items.length === 0}>
              Stage for Inspection
            </button>
          )}
        </div>
      </div>

      <div style={{ marginBottom: '2rem', padding: '1rem', backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
        <p><strong>Status:</strong> {grn.status}</p>
        <p><strong>Received Date:</strong> {new Date(grn.received_date).toLocaleDateString()}</p>
        <p><strong>Supplier Delivery Ref:</strong> {grn.delivery_reference || 'N/A'}</p>
      </div>

      {grn.status === 'RECEIVING' && spo && (
        <div style={{ marginBottom: '2rem', padding: '1rem', backgroundColor: '#f9fafb', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
          <h3 style={{ marginTop: 0 }}>Receive Line Item</h3>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Select SPO Item</label>
              <select value={selectedSpoItemId} onChange={e => setSelectedSpoItemId(e.target.value)} style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc' }}>
                <option value="">-- Select Item --</option>
                {spo.items.map((item: any) => (
                  <option key={item.id} value={item.id}>
                    {item.internal_sku} - {item.description} (Ordered: {item.quantity_ordered}, Confirmed: {item.quantity_confirmed})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.875rem', marginBottom: '0.25rem' }}>Qty Received</label>
              <input type="number" value={qtyReceivedInput} onChange={e => setQtyReceivedInput(Number(e.target.value))} style={{ width: '150px', padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc' }} />
            </div>
            <button className={styles.primaryBtn} onClick={handleAddItem} disabled={addItemMutation.isPending}>
              Add Item
            </button>
          </div>
        </div>
      )}

      <h3>Items</h3>
      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>SKU / Product</th>
              <th>Ordered / Confirmed</th>
              <th>Received</th>
              {grn.status === 'PENDING_INSPECTION' && (
                <>
                  <th>Disposition (Acc / Dam / Rej)</th>
                  <th>Action</th>
                </>
              )}
              {['PARTIALLY_ACCEPTED', 'ACCEPTED', 'PARTIALLY_REJECTED', 'REJECTED'].includes(grn.status) && (
                <th>Result (Acc / Dam / Rej)</th>
              )}
            </tr>
          </thead>
          <tbody>
            {grn.items.map((item) => (
              <tr key={item.id}>
                <td>
                  <strong>{item.internal_sku}</strong><br/>
                  <span style={{ fontSize: '0.875rem', color: '#6b7280' }}>{item.description}</span>
                </td>
                <td>{Number(item.quantity_ordered_snapshot)} / {Number(item.quantity_confirmed_snapshot)}</td>
                <td><strong>{Number(item.quantity_received)}</strong></td>

                {grn.status === 'PENDING_INSPECTION' && !item.status?.includes('ACCEPTED') && !item.status?.includes('REJECTED') && (
                  <>
                    <td style={{ minWidth: '400px' }}>
                      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <Controller
                          name={`${item.id}.quantity_accepted`}
                          control={control}
                          defaultValue={0}
                          render={({ field }) => <input {...field} type="number" placeholder="Acc" style={{ width: '80px', padding: '4px' }} />}
                        />
                        <Controller
                          name={`${item.id}.quantity_damaged`}
                          control={control}
                          defaultValue={0}
                          render={({ field }) => <input {...field} type="number" placeholder="Dam" style={{ width: '80px', padding: '4px' }} />}
                        />
                        <Controller
                          name={`${item.id}.quantity_rejected`}
                          control={control}
                          defaultValue={0}
                          render={({ field }) => <input {...field} type="number" placeholder="Rej" style={{ width: '80px', padding: '4px' }} />}
                        />
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                         <Controller
                          name={`${item.id}.damage_reason`}
                          control={control}
                          defaultValue={""}
                          render={({ field }) => <input {...field} type="text" placeholder="Damage Reason" style={{ flex: 1, padding: '4px' }} />}
                        />
                         <Controller
                          name={`${item.id}.rejection_reason`}
                          control={control}
                          defaultValue={""}
                          render={({ field }) => <input {...field} type="text" placeholder="Rejection Reason" style={{ flex: 1, padding: '4px' }} />}
                        />
                      </div>
                    </td>
                    <td>
                      <button className={styles.primaryBtn} onClick={handleSubmit((data) => handleDispositionSubmit(item.id, data))}>
                        Record
                      </button>
                    </td>
                  </>
                )}

                {grn.status === 'PENDING_INSPECTION' && (item.status?.includes('ACCEPTED') || item.status?.includes('REJECTED') || (Number(item.quantity_accepted) + Number(item.quantity_damaged) + Number(item.quantity_rejected) > 0)) && (
                   <td colSpan={2}>
                    <span style={{ color: '#166534', fontWeight: 'bold' }}>{Number(item.quantity_accepted)}</span> /{' '}
                    <span style={{ color: '#b45309', fontWeight: 'bold' }}>{Number(item.quantity_damaged)}</span> /{' '}
                    <span style={{ color: '#991b1b', fontWeight: 'bold' }}>{Number(item.quantity_rejected)}</span>
                  </td>
                )}

                {['PARTIALLY_ACCEPTED', 'ACCEPTED', 'PARTIALLY_REJECTED', 'REJECTED'].includes(grn.status) && (
                  <td>
                    <span style={{ color: '#166534', fontWeight: 'bold' }}>{Number(item.quantity_accepted)}</span> /{' '}
                    <span style={{ color: '#b45309', fontWeight: 'bold' }}>{Number(item.quantity_damaged)}</span> /{' '}
                    <span style={{ color: '#991b1b', fontWeight: 'bold' }}>{Number(item.quantity_rejected)}</span>
                  </td>
                )}
              </tr>
            ))}
            {grn.items.length === 0 && (
              <tr><td colSpan={5} style={{ textAlign: 'center', padding: '1rem' }}>No items</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
