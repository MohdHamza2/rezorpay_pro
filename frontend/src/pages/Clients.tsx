import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getClients,
  getClientCredit,
  createClient,
  updateClient,
  deleteClient,
} from '../api/clients';
import type { Client } from '../api/clients';
import { Edit2, Trash2, Plus } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import toast from 'react-hot-toast';
import { Skeleton } from '../components/Skeleton';
import { formatAed } from './quotationHelpers';
import { CreditStatusBadge } from './CreditStatusBadge';
import {
  PAYMENT_TERMS_DAYS,
  buildClientWritePayload,
  clientSchema,
  creditLimitFieldValue,
  isPaymentTermsDays,
  type ClientFormValues,
} from './clientHelpers';
import styles from './Clients.module.css';

const BLANK_FORM: ClientFormValues = {
  name: '',
  email: '',
  phone: '',
  address: '',
  tax_id: '',
  credit_limit: '',
  payment_terms_days: 0,
};

function formFromClient(client: Client): ClientFormValues {
  const terms = client.payment_terms_days ?? 0;
  return {
    name: client.name,
    email: client.email,
    phone: client.phone || '',
    address: client.address || '',
    tax_id: client.tax_id || '',
    credit_limit: creditLimitFieldValue(client.credit_limit),
    payment_terms_days: isPaymentTermsDays(terms) ? terms : 0,
  };
}

export const Clients = () => {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingClient, setEditingClient] = useState<Client | null>(null);

  const { data: clients, isLoading } = useQuery({
    queryKey: ['clients'],
    queryFn: getClients,
  });
  const { data: credit } = useQuery({
    queryKey: ['client-credit', editingClient?.id],
    queryFn: () => getClientCredit(editingClient!.id),
    enabled: Boolean(editingClient?.id),
  });

  const createMutation = useMutation({
    mutationFn: createClient,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      closeModal();
      toast.success('Client created successfully');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ReturnType<typeof buildClientWritePayload> }) =>
      updateClient(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      queryClient.invalidateQueries({ queryKey: ['client-credit'] });
      closeModal();
      toast.success('Client updated successfully');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteClient,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      toast.success('Client deleted successfully');
    },
  });

  const { register, handleSubmit, reset, formState: { errors } } = useForm<ClientFormValues>({
    resolver: zodResolver(clientSchema),
    defaultValues: BLANK_FORM,
  });

  const openModal = (client?: Client) => {
    if (client) {
      setEditingClient(client);
      reset(formFromClient(client));
    } else {
      setEditingClient(null);
      reset(BLANK_FORM);
    }
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingClient(null);
    reset(BLANK_FORM);
  };

  const onSubmit = (data: ClientFormValues) => {
    const payload = buildClientWritePayload(data, editingClient ? 'update' : 'create');
    if (editingClient) {
      updateMutation.mutate({ id: editingClient.id, data: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Clients</h2>
        <button className={styles.primaryBtn} data-testid="client-add" onClick={() => openModal()}>
          <Plus size={16} style={{ display: 'inline', marginRight: '0.5rem', verticalAlign: 'middle' }} />
          Add Client
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
                <th>Name</th>
                <th>Email</th>
                <th>Credit</th>
                <th>Unapplied credit</th>
                <th>Exposure / limit</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {clients?.map((client) => (
                <tr key={client.id} data-testid={`client-row-${client.name}`}>
                  <td>{client.name}</td>
                  <td>{client.email}</td>
                  <td><CreditStatusBadge status={client.credit_status} /></td>
                  <td data-testid="client-credit-balance">
                    {client.credit_balance != null ? formatAed(client.credit_balance) : '—'}
                  </td>
                  <td data-testid="client-credit-exposure">
                    {formatAed(client.exposure)} / {formatAed(client.effective_credit_limit)}
                  </td>
                  <td>
                    <Link
                      to={`/clients/${client.id}/statement`}
                      className={styles.statementLink}
                      data-testid="client-statement"
                    >
                      Statement
                    </Link>
                    <button className={styles.actionBtn} onClick={() => openModal(client)}>
                      <Edit2 size={16} />
                    </button>
                    <button
                      className={`${styles.actionBtn} ${styles.delete}`}
                      onClick={() => {
                        if (window.confirm('Are you sure you want to delete this client?')) {
                          deleteMutation.mutate(client.id);
                        }
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {clients?.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>
                    No clients found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {isModalOpen && (
        <div className={styles.modalOverlay} data-testid="client-modal">
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <h3>{editingClient ? 'Edit Client' : 'Add Client'}</h3>
              <button className={styles.closeBtn} onClick={closeModal}>&times;</button>
            </div>
            <form onSubmit={handleSubmit(onSubmit)}>
              <div className={styles.formGroup}>
                <label>Name</label>
                <input data-testid="client-name" {...register('name')} />
                {errors.name && <span className={styles.errorText}>{errors.name.message}</span>}
              </div>
              <div className={styles.formGroup}>
                <label>Email</label>
                <input type="email" data-testid="client-email" {...register('email')} />
                {errors.email && <span className={styles.errorText}>{errors.email.message}</span>}
              </div>
              <div className={styles.formGroup}>
                <label>Phone</label>
                <input {...register('phone')} />
                {errors.phone && <span className={styles.errorText}>{errors.phone.message}</span>}
              </div>
              <div className={styles.formGroup}>
                <label htmlFor="client-tax-id">TRN (Tax Registration Number)</label>
                <input id="client-tax-id" data-testid="client-tax-id" {...register('tax_id')} />
                <span className={styles.hint}>Buyer TRN. Required to send a standard (B2B) tax invoice.</span>
                {errors.tax_id && <span className={styles.errorText}>{errors.tax_id.message}</span>}
              </div>
              <div className={styles.formGroup}>
                <label>Address</label>
                <input data-testid="client-address" {...register('address')} />
                <span className={styles.hint}>Required to send a standard (B2B) tax invoice.</span>
                {errors.address && <span className={styles.errorText}>{errors.address.message}</span>}
              </div>
              <div className={styles.formGroup}>
                <label htmlFor="client-credit-limit">Credit limit (AED)</label>
                <input
                  id="client-credit-limit"
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="Inherit workspace default"
                  data-testid="client-credit-limit"
                  {...register('credit_limit')}
                />
                <span className={styles.hint}>Leave blank to inherit workspace default. 0 is COD.</span>
                {errors.credit_limit && <span className={styles.errorText}>{errors.credit_limit.message}</span>}
              </div>
              <div className={styles.formGroup}>
                <label htmlFor="client-payment-terms">Payment terms</label>
                <select
                  id="client-payment-terms"
                  data-testid="client-payment-terms"
                  {...register('payment_terms_days', { valueAsNumber: true })}
                >
                  {PAYMENT_TERMS_DAYS.map((days) => (
                    <option key={days} value={days}>
                      {days === 0 ? '0 — COD (due on issue)' : `Net ${days}`}
                    </option>
                  ))}
                </select>
                {errors.payment_terms_days && (
                  <span className={styles.errorText}>{errors.payment_terms_days.message}</span>
                )}
              </div>
              {editingClient && (
                <div className={styles.creditPanel} data-testid="client-credit-panel">
                  <div className={styles.creditPanelHead}>
                    <CreditStatusBadge status={credit?.credit_status ?? editingClient.credit_status} />
                    <span>
                      {formatAed(credit?.exposure ?? editingClient.exposure)} /{' '}
                      {formatAed(credit?.effective_credit_limit ?? editingClient.effective_credit_limit)}
                    </span>
                  </div>
                  {credit?.oldest_overdue_days != null && (
                    <span className={styles.hint}>Oldest overdue: {credit.oldest_overdue_days} days</span>
                  )}
                  {credit?.buckets && (
                    <div className={styles.agingGrid}>
                      <span>Current {formatAed(credit.buckets.current)}</span>
                      <span>1–30 {formatAed(credit.buckets.days_1_30)}</span>
                      <span>31–60 {formatAed(credit.buckets.days_31_60)}</span>
                      <span>61–90 {formatAed(credit.buckets.days_61_90)}</span>
                      <span>90+ {formatAed(credit.buckets.days_90_plus)}</span>
                    </div>
                  )}
                  {(credit?.credit_balance != null || editingClient.credit_balance != null) && (
                    <span className={styles.hint} data-testid="client-credit-balance">
                      Unapplied credit (credit notes, not cash):{' '}
                      {formatAed(credit?.credit_balance ?? editingClient.credit_balance)}
                      . Not applied to the next invoice in this release.
                    </span>
                  )}
                </div>
              )}
              <div className={styles.modalActions}>
                <button type="button" className={styles.secondaryBtn} onClick={closeModal}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className={styles.primaryBtn}
                  data-testid="client-form-submit"
                  disabled={createMutation.isPending || updateMutation.isPending}
                >
                  {editingClient ? 'Update' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
