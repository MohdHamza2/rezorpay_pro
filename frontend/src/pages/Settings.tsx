import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getCurrentWorkspace, updateCurrentWorkspace } from '../api/workspaces';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import toast from 'react-hot-toast';
import { useEffect } from 'react';
import styles from './Settings.module.css';
import { Skeleton } from '../components/Skeleton';

const settingsSchema = z.object({
  name: z.string().min(1, 'Workspace name is required'),
  trn: z.string().optional().nullable(),
  whatsapp_number: z.string().optional().nullable(),
  default_tax_rate: z.number().min(0).max(100),
  credit_limit_default: z.number().min(0),
  credit_hold_days: z.number().min(0)
});

type SettingsValues = z.infer<typeof settingsSchema>;

export const Settings = () => {
  const queryClient = useQueryClient();
  const { data: workspace, isLoading } = useQuery({ queryKey: ['workspace'], queryFn: getCurrentWorkspace });

  const { register, handleSubmit, reset, formState: { errors } } = useForm<SettingsValues>({
    resolver: zodResolver(settingsSchema)
  });

  useEffect(() => {
    if (workspace) {
      reset({
        name: workspace.name,
        trn: workspace.trn,
        whatsapp_number: workspace.whatsapp_number,
        default_tax_rate: Number(workspace.default_tax_rate ?? 5),
        credit_limit_default: Number(workspace.credit_limit_default ?? 0),
        credit_hold_days: workspace.credit_hold_days
      });
    }
  }, [workspace, reset]);

  const updateMutation = useMutation({
    mutationFn: (data: SettingsValues) => updateCurrentWorkspace(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace'] });
      toast.success('Settings updated successfully');
    },
    onError: () => {
      toast.error('Failed to update settings');
    }
  });

  const onSubmit = (data: SettingsValues) => {
    updateMutation.mutate(data);
  };

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.header}><h2>Workspace Settings</h2></div>
        <Skeleton height="300px" />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Workspace Settings</h2>
      </div>

      <form onSubmit={handleSubmit(onSubmit)}>
        <div className={styles.card}>
          <h3 className={styles.cardTitle}>General Information</h3>
          <div className={styles.grid}>
            <div className={styles.formGroup}>
              <label>Workspace Name</label>
              <input type="text" {...register('name')} />
              {errors.name && <span className={styles.errorText}>{errors.name.message}</span>}
            </div>
            <div className={styles.formGroup}>
              <label htmlFor="settings-trn">TRN (Tax Registration Number)</label>
              <input id="settings-trn" type="text" data-testid="settings-trn" {...register('trn')} />
              {errors.trn && <span className={styles.errorText}>{errors.trn.message}</span>}
            </div>
            <div className={styles.formGroup}>
              <label>WhatsApp Number</label>
              <input type="text" {...register('whatsapp_number')} placeholder="+971..." />
              {errors.whatsapp_number && <span className={styles.errorText}>{errors.whatsapp_number.message}</span>}
            </div>
          </div>
        </div>

        <div className={styles.card}>
          <h3 className={styles.cardTitle}>Financial & Tax Defaults</h3>
          <div className={styles.grid}>
            <div className={styles.formGroup}>
              <label htmlFor="settings-tax-rate">Default Tax Rate (%)</label>
              <input
                id="settings-tax-rate"
                type="number"
                step="0.01"
                data-testid="settings-tax-rate"
                {...register('default_tax_rate', { valueAsNumber: true })}
              />
              {errors.default_tax_rate && <span className={styles.errorText}>{errors.default_tax_rate.message}</span>}
            </div>
            <div className={styles.formGroup}>
              <label>Default Credit Limit (AED)</label>
              <input type="number" step="0.01" {...register('credit_limit_default', { valueAsNumber: true })} />
              {errors.credit_limit_default && <span className={styles.errorText}>{errors.credit_limit_default.message}</span>}
            </div>
            <div className={styles.formGroup}>
              <label>Credit Hold Days (Overdue before block)</label>
              <input type="number" {...register('credit_hold_days', { valueAsNumber: true })} />
              {errors.credit_hold_days && <span className={styles.errorText}>{errors.credit_hold_days.message}</span>}
            </div>
          </div>
        </div>

        <div className={styles.actions} style={{ maxWidth: '800px' }}>
          <button type="submit" className={styles.primaryBtn} disabled={updateMutation.isPending}>
            {updateMutation.isPending ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </form>
    </div>
  );
};
