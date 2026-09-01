import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { isHttpNotFound } from '../api/errors';
import { listPayments, postPdcAction, type Payment, type PdcAction } from '../api/invoices';
import { useAuth } from '../contexts/AuthContext';
import {
  canManagePdc,
  isUnclearedPdc,
  legalPdcActions,
  PDC_ACTION_LABEL,
  pdcActionMessage,
} from './paymentHelpers';
import { formatAed } from './quotationHelpers';
import styles from './Invoices.module.css';

type Props = { invoiceId: string };

function invalidatePaymentQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  invoiceId: string,
) {
  queryClient.invalidateQueries({ queryKey: ['invoice-payments', invoiceId] });
  queryClient.invalidateQueries({ queryKey: ['invoice', invoiceId] });
  queryClient.invalidateQueries({ queryKey: ['invoices'] });
  queryClient.invalidateQueries({ queryKey: ['clients'] });
}

function PdcActionButtons({
  payment,
  busy,
  onAction,
}: {
  payment: Payment;
  busy: boolean;
  onAction: (action: PdcAction) => void;
}) {
  const actions = legalPdcActions(payment);
  if (actions.length === 0) return null;
  return (
    <div className={styles.pdcActions}>
      {actions.map((action) => (
        <button
          key={action}
          type="button"
          className={action === 'bounce' || action === 'return' ? styles.pdcDanger : styles.pdcBtn}
          data-testid={`pdc-${action}`}
          disabled={busy}
          onClick={() => onAction(action)}
        >
          {PDC_ACTION_LABEL[action]}
        </button>
      ))}
    </div>
  );
}

function PaymentRow({
  payment,
  showActions,
  busy,
  onAction,
}: {
  payment: Payment;
  showActions: boolean;
  busy: boolean;
  onAction: (action: PdcAction) => void;
}) {
  const pending = isUnclearedPdc(payment);
  return (
    <tr data-testid={`payment-row-${payment.id}`} className={pending ? styles.paymentPending : undefined}>
      <td>{payment.payment_method}</td>
      <td>{formatAed(payment.amount)}</td>
      <td>
        {payment.status}
        {pending ? ' (not cash)' : null}
      </td>
      <td>{payment.pdc_status ?? '—'}</td>
      <td>
        {showActions ? (
          <PdcActionButtons payment={payment} busy={busy} onAction={onAction} />
        ) : null}
      </td>
    </tr>
  );
}

export function InvoicePayments({ invoiceId }: Props) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const showActions = canManagePdc(user?.role);
  const { data: payments, isLoading } = useQuery({
    queryKey: ['invoice-payments', invoiceId],
    queryFn: () => listPayments(invoiceId),
    retry: (count, err) => !isHttpNotFound(err) && count < 2,
  });
  const mutation = useMutation({
    mutationFn: ({ paymentId, action }: { paymentId: string; action: PdcAction }) =>
      postPdcAction(invoiceId, paymentId, action),
    onSuccess: (_row, vars) => {
      invalidatePaymentQueries(queryClient, invoiceId);
      toast.success(pdcActionMessage(vars.action));
    },
  });

  if (isLoading) return <p>Loading payments…</p>;
  const rows = payments ?? [];
  return (
    <div data-testid="payment-list">
      <h4 className={styles.paymentHeading}>Payments</h4>
      <p className={styles.hint}>
        Uncleared PDC is pending and is not cash. Amount paid is SUCCESS only.
      </p>
      {rows.length === 0 ? (
        <p className={styles.hint}>No payments yet.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Method</th>
              <th>Amount</th>
              <th>Status</th>
              <th>PDC</th>
              <th>{showActions ? 'Actions' : ''}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((payment) => (
              <PaymentRow
                key={payment.id}
                payment={payment}
                showActions={showActions}
                busy={mutation.isPending}
                onAction={(action) => mutation.mutate({ paymentId: payment.id, action })}
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
