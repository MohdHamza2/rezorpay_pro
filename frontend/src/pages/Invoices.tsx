import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getInvoices, createInvoice, updateInvoice, sendInvoice, voidInvoice, recordPayment } from '../api/invoices';
import type { Invoice, InvoiceStatus } from '../api/invoices';
import { getClients } from '../api/clients';
import { useForm, useFieldArray } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Edit2, Plus, Trash2, Send, XCircle, DollarSign, Download } from 'lucide-react';
import { PDFDownloadLink } from '@react-pdf/renderer';
import { InvoicePDF } from '../components/pdf/InvoicePDF';
import { getCurrentWorkspace } from '../api/workspaces';
import toast from 'react-hot-toast';
import { Skeleton } from '../components/Skeleton';
import styles from './Invoices.module.css';

const invoiceItemSchema = z.object({
  description: z.string().min(1, 'Description required'),
  quantity: z.number().min(1),
  unit_price: z.number().min(0),
});

const invoiceSchema = z.object({
  client_id: z.string().min(1, 'Client required'),
  issue_date: z.string().min(1, 'Issue date required'),
  due_date: z.string().min(1, 'Due date required'),
  items: z.array(invoiceItemSchema).min(1, 'At least one item required'),
});

type InvoiceFormValues = z.infer<typeof invoiceSchema>;

export const Invoices = () => {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingInvoice, setEditingInvoice] = useState<Invoice | null>(null);
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [paymentInvoice, setPaymentInvoice] = useState<Invoice | null>(null);
  const [paymentAmount, setPaymentAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('BANK_TRANSFER');
  const [referenceNumber, setReferenceNumber] = useState('');
  const [bankName, setBankName] = useState('');
  const [pdcDate, setPdcDate] = useState('');

  
  const { data: invoices, isLoading } = useQuery({ queryKey: ['invoices'], queryFn: getInvoices });
  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
    const { data: workspace } = useQuery({ queryKey: ['workspace'], queryFn: getCurrentWorkspace });

    const paymentMutation = useMutation({
    mutationFn: ({ id, data }: { id: string, data: any }) => recordPayment(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      setIsPaymentModalOpen(false);
      setPaymentInvoice(null);
      setPaymentAmount('');
        setReferenceNumber('');
        setBankName('');
        setPdcDate('');
    },
    onError: (err: any) => {
      alert(err.response?.data?.detail || 'Failed to record payment');
    }
  });

  const createMutation = useMutation({
    mutationFn: createInvoice,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['invoices'] }); closeModal(); toast.success('Invoice created'); },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Invoice> }) => updateInvoice(id, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['invoices'] }); closeModal(); toast.success('Invoice updated'); },
  });

  const actionMutation = useMutation({
    mutationFn: ({ id, action, payload }: { id: string, action: 'send' | 'void', payload?: any }) => action === 'send' ? sendInvoice(id, { recipient: 'test@example.com' }) : voidInvoice(id, payload?.reason || 'Cancelled'),
    onSuccess: (_, variables) => { 
      queryClient.invalidateQueries({ queryKey: ['invoices'] }); 
      toast.success(`Invoice ${variables.action === 'send' ? 'sent' : 'voided'}`);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail?.[0]?.msg || error.response?.data?.detail || 'Action failed');
    }
  });

  const { register, control, handleSubmit, reset, formState: { errors } } = useForm<InvoiceFormValues>({
    resolver: zodResolver(invoiceSchema),
    defaultValues: { items: [{ description: '', quantity: 1, unit_price: 0 }] }
  });

  const { fields, append, remove } = useFieldArray({ control, name: 'items' });

  const openModal = (invoice?: Invoice) => {
    if (invoice) {
      setEditingInvoice(invoice);
      reset({
        client_id: invoice.client_id,
        issue_date: invoice.issue_date,
        due_date: invoice.due_date,
        items: invoice.items.map(i => ({ description: i.description, quantity: i.quantity, unit_price: i.unit_price }))
      });
    } else {
      setEditingInvoice(null);
      reset({
        client_id: '',
        issue_date: new Date().toISOString().split('T')[0],
        due_date: new Date(Date.now() + 30*24*60*60*1000).toISOString().split('T')[0],
        items: [{ description: '', quantity: 1, unit_price: 0 }]
      });
    }
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingInvoice(null);
  };

  const onSubmit = (data: InvoiceFormValues) => {
    const items = data.items.map(i => ({ description: i.description, quantity: i.quantity, unit_price: i.unit_price, total_price: i.quantity * i.unit_price }));
    const payload: any = { ...data, items };

    if (editingInvoice) {
      updateMutation.mutate({ id: editingInvoice.id, data: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  const getStatusBadge = (status: InvoiceStatus) => {
    const map = {
      DRAFT: styles.badgeDraft,
      SENT: styles.badgeSent,
      PARTIALLY_PAID: styles.badgePartial,
      PAID: styles.badgePaid,
      CANCELLED: styles.badgeCancelled
    };
    return <span className={`${styles.badge} ${map[status]}`}>{status.replace('_', ' ')}</span>;
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Invoices</h2>
        <button className={styles.primaryBtn} onClick={() => openModal()}>
          <Plus size={16} style={{ display: 'inline', marginRight: '0.5rem', verticalAlign: 'middle' }} />
          Create Invoice
        </button>
      </div>

      <div className={styles.tableContainer}>
        {isLoading ? (
          <div style={{ padding: '2rem' }}>
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} height="40px" style={{ marginBottom: '1rem' }} />
            ))}
          </div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Invoice #</th>
                <th>Client</th>
                <th>Status</th>
                <th>Total</th>
                <th>Amount Due</th>
                <th>Issue Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {invoices?.map((inv) => {
                const client = clients?.find(c => c.id === inv.client_id);
                const amountDue = inv.balance_due || 0;
                return (
                  <tr key={inv.id}>
                    <td><strong>{inv.invoice_number}</strong></td>
                    <td>{client?.name || 'Unknown Client'}</td>
                    <td>{getStatusBadge(inv.status)}</td>
                    <td>AED {Number(inv.total_amount || 0).toFixed(2)}</td>
                    <td>AED {Number(amountDue || 0).toFixed(2)}</td>
                    <td>{new Date(inv.issue_date).toLocaleDateString()}</td>
                    <td>
                      
                          <PDFDownloadLink
                            document={<InvoicePDF invoice={inv} client={clients?.find(c => c.id === inv.client_id)} workspace={workspace} />}
                            fileName={`Invoice_${inv.invoice_number}.pdf`}
                          >
                            {({ loading }) => (
                              <button className={styles.actionBtn} disabled={loading} title="Download PDF">
                                <Download size={16} />
                              </button>
                            )}
                          </PDFDownloadLink>
                        {inv.status === 'DRAFT' && (
                        <>
                          <button className={styles.actionBtn} onClick={() => openModal(inv)} title="Edit">
                            <Edit2 size={16} />
                          </button>
                          <button className={styles.actionBtn} onClick={() => actionMutation.mutate({ id: inv.id, action: 'send'})} title="Mark as Sent">
                            <Send size={16} />
                          </button>
                          <button className={styles.actionBtn} onClick={() => {
                            const reason = window.prompt('Reason for voiding? (min 5 chars)');
                            if (reason && reason.length >= 5) {
                              actionMutation.mutate({ id: inv.id, action: 'void', payload: { reason } } as any);
                            } else if (reason) {
                              alert('Reason must be at least 5 characters');
                            }
                          }} title="Void">
                            <XCircle size={16} />
                          </button>
                        </>
                      )}
                      {inv.status === 'SENT' && (
                        <button className={styles.actionBtn} onClick={() => { setPaymentInvoice(inv); setPaymentAmount(amountDue.toFixed(2)); setIsPaymentModalOpen(true); }} title="Record Payment">
                          <DollarSign size={16} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {invoices?.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '2rem' }}>No invoices found.</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {isModalOpen && (
        <div className={styles.modalOverlay}>
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <h3>{editingInvoice ? 'Edit Invoice' : 'Create Invoice'}</h3>
              <button className={styles.closeBtn} onClick={closeModal}>&times;</button>
            </div>
            <form onSubmit={handleSubmit(onSubmit)}>
              <div className={styles.grid2}>
                <div className={styles.formGroup}>
                  <label>Client</label>
                  <select {...register('client_id')}>
                    <option value="">Select a client...</option>
                    {clients?.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                  {errors.client_id && <span className={styles.errorText}>{errors.client_id.message}</span>}
                </div>
                <div className={styles.formGroup}>
                  <label>Issue Date</label>
                  <input type="date" {...register('issue_date')} />
                  {errors.issue_date && <span className={styles.errorText}>{errors.issue_date.message}</span>}
                </div>
                <div className={styles.formGroup}>
                  <label>Due Date</label>
                  <input type="date" {...register('due_date')} />
                  {errors.due_date && <span className={styles.errorText}>{errors.due_date.message}</span>}
                </div>
              </div>

              <div className={styles.itemsSection}>
                <div className={styles.itemsHeader}>
                  <h4>Line Items</h4>
                  <button type="button" className={styles.secondaryBtn} onClick={() => append({ description: '', quantity: 1, unit_price: 0 })}>
                    Add Item
                  </button>
                </div>
                {fields.map((field, index) => (
                  <div key={field.id} className={styles.itemRow}>
                    <div className={styles.formGroup}>
                      <label>Description</label>
                      <input {...register(`items.${index}.description` as const)} />
                      {errors.items?.[index]?.description && <span className={styles.errorText}>{errors.items[index].description.message}</span>}
                    </div>
                    <div className={styles.formGroup}>
                      <label>Qty</label>
                      <input type="number" step="0.01" {...register(`items.${index}.quantity` as const, { valueAsNumber: true })} />
                    </div>
                    <div className={styles.formGroup}>
                      <label>Price</label>
                      <input type="number" step="0.01" {...register(`items.${index}.unit_price` as const, { valueAsNumber: true })} />
                    </div>
                    <button type="button" className={styles.removeBtn} onClick={() => remove(index)} disabled={fields.length === 1}>
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
                {errors.items?.root && <span className={styles.errorText}>{errors.items.root.message}</span>}
              </div>

              <div className={styles.modalActions}>
                <button type="button" className={styles.secondaryBtn} onClick={closeModal}>Cancel</button>
                <button type="submit" className={styles.primaryBtn} disabled={createMutation.isPending || updateMutation.isPending}>
                  {editingInvoice ? 'Update Invoice' : 'Create Invoice'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

              {isPaymentModalOpen && paymentInvoice && (
          <div className={styles.modalOverlay}>
            <div className={styles.modal} style={{ maxWidth: '500px' }}>
              <div className={styles.modalHeader}>
                <h3>Record Payment</h3>
                <button className={styles.closeBtn} onClick={() => setIsPaymentModalOpen(false)}>&times;</button>
              </div>
              <div className={styles.formGroup} style={{ marginTop: '1rem' }}>
                <label>Amount (AED)</label>
                <input type="number" step="0.01" value={paymentAmount} onChange={(e) => setPaymentAmount(e.target.value)} />
              </div>
              <div className={styles.formGroup}>
                <label>Payment Method</label>
                <select value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)}>
                  <option value="BANK_TRANSFER">Bank Transfer</option>
                  <option value="CASH">Cash</option>
                  <option value="CREDIT_CARD">Credit Card</option>
                  <option value="CHEQUE">Cheque</option>
                  <option value="PDC">Post-Dated Cheque (PDC)</option>
                </select>
              </div>
              
              {(paymentMethod === 'CHEQUE' || paymentMethod === 'PDC' || paymentMethod === 'BANK_TRANSFER') && (
                <div className={styles.formGroup}>
                  <label>{paymentMethod === 'BANK_TRANSFER' ? 'Transaction Ref' : 'Cheque Number'}</label>
                  <input type="text" value={referenceNumber} onChange={(e) => setReferenceNumber(e.target.value)} />
                </div>
              )}
              
              {(paymentMethod === 'CHEQUE' || paymentMethod === 'PDC') && (
                <div className={styles.formGroup}>
                  <label>Bank Name</label>
                  <input type="text" value={bankName} onChange={(e) => setBankName(e.target.value)} />
                </div>
              )}
              
              {paymentMethod === 'PDC' && (
                <div className={styles.formGroup}>
                  <label>PDC Date</label>
                  <input type="date" value={pdcDate} onChange={(e) => setPdcDate(e.target.value)} />
                </div>
              )}

              <div className={styles.modalActions}>
                <button type="button" className={styles.secondaryBtn} onClick={() => setIsPaymentModalOpen(false)}>Cancel</button>
                <button type="button" className={styles.primaryBtn} disabled={paymentMutation.isPending || !paymentAmount} onClick={() => {
                  const data: any = { amount: parseFloat(paymentAmount), payment_method: paymentMethod };
                  if (referenceNumber) data.reference_number = referenceNumber;
                  if (bankName) data.bank_name = bankName;
                  if (paymentMethod === 'PDC') {
                     data.pdc_date = pdcDate;
                     data.pdc_status = 'RECEIVED';
                  }
                  paymentMutation.mutate({ id: paymentInvoice.id, data });
                }}>
                  {paymentMutation.isPending ? 'Recording...' : 'Record Payment'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
};
