import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getClients, createClient, updateClient, deleteClient } from '../api/clients';
import type { Client } from '../api/clients';
import { Edit2, Trash2, Plus } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import toast from 'react-hot-toast';
import { Skeleton } from '../components/Skeleton';
import styles from './Clients.module.css';

const clientSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters'),
  email: z.string().email('Invalid email address'),
  phone: z.string().optional(),
  address: z.string().optional(),
  tax_id: z.string().optional(),
});

type ClientFormValues = z.infer<typeof clientSchema>;

export const Clients = () => {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingClient, setEditingClient] = useState<Client | null>(null);

  const { data: clients, isLoading } = useQuery({
    queryKey: ['clients'],
    queryFn: getClients,
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
    mutationFn: ({ id, data }: { id: string; data: Partial<Client> }) => updateClient(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
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
  });

  const openModal = (client?: Client) => {
    if (client) {
      setEditingClient(client);
      reset({
        name: client.name,
        email: client.email,
        phone: client.phone || '',
        address: client.address || '',
        tax_id: client.tax_id || '',
      });
    } else {
      setEditingClient(null);
      reset({ name: '', email: '', phone: '', address: '', tax_id: '' });
    }
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingClient(null);
    reset();
  };

  const onSubmit = (data: ClientFormValues) => {
    if (editingClient) {
      updateMutation.mutate({ id: editingClient.id, data });
    } else {
      createMutation.mutate(data);
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
                <th>Phone</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {clients?.map((client) => (
                <tr key={client.id} data-testid={`client-row-${client.name}`}>
                  <td>{client.name}</td>
                  <td>{client.email}</td>
                  <td>{client.phone || '-'}</td>
                  <td>{new Date(client.created_at).toLocaleDateString()}</td>
                  <td>
                    <button className={styles.actionBtn} onClick={() => openModal(client)}>
                      <Edit2 size={16} />
                    </button>
                    <button
                      className={`${styles.actionBtn} ${styles.delete}`}
                      onClick={() => {
                        if(window.confirm('Are you sure you want to delete this client?')) {
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
                  <td colSpan={5} style={{ textAlign: 'center', padding: '2rem' }}>
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
