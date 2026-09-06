import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowLeft } from 'lucide-react';
import { getClients } from '../../api/clients';
import {
  convertEnquiryToQuotation,
  getEnquiry,
  updateEnquiryStatus,
  type EnquiryStatus,
} from '../../api/enquiries';
import styles from './Enquiries.module.css';

const StatusBadge = ({ status }: { status: EnquiryStatus }) => {
  const mapping: Record<EnquiryStatus, string> = {
    NEW: styles.badgeNew,
    IN_PROGRESS: styles.badgeInProgress,
    QUOTED: styles.badgeQuoted,
    CLOSED: styles.badgeClosed,
  };
  return <span className={`${styles.badge} ${mapping[status]}`}>{status.replace('_', ' ')}</span>;
};

export const EnquiryDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: enquiry, isLoading } = useQuery({
    queryKey: ['enquiry', id],
    queryFn: () => getEnquiry(id!),
    enabled: Boolean(id),
  });

  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['enquiries'] });
    queryClient.invalidateQueries({ queryKey: ['enquiry', id] });
  };

  const statusMutation = useMutation({
    mutationFn: (newStatus: EnquiryStatus) => updateEnquiryStatus(id!, newStatus),
    onSuccess: () => {
      invalidate();
      toast.success('Status updated');
    },
    onError: () => {
      toast.error('Failed to update status');
    }
  });

  const convertMutation = useMutation({
    mutationFn: () => convertEnquiryToQuotation(id!),
    onSuccess: (quotation) => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ['quotations'] });
      toast.success(`Converted to Quotation ${quotation.quotation_number}`);
      navigate(`/quotations/${quotation.id}`);
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.error?.message || 'Failed to convert to quotation');
    }
  });

  if (isLoading) {
    return <div style={{ padding: '2rem' }}>Loading...</div>;
  }

  if (!enquiry) {
    return <div style={{ padding: '2rem' }}>Enquiry not found.</div>;
  }

  const client = clients?.find((c) => c.id === enquiry.client_id);
  const clientName = client ? client.name : enquiry.contact_name || 'No Contact Info';

  return (
    <div className={styles.container}>
      <button
        className={styles.iconBtn}
        style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        onClick={() => navigate('/enquiries')}
      >
        <ArrowLeft size={16} /> Back to Enquiries
      </button>

      <div className={styles.header}>
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            {enquiry.enquiry_number}
            <StatusBadge status={enquiry.status} />
          </h2>
          <div style={{ color: '#6b7280', fontSize: '0.875rem', marginTop: '0.25rem' }}>
            Created {new Date(enquiry.created_at).toLocaleString()} • Source: {enquiry.source}
          </div>
        </div>

        <div className={styles.actions}>
          {enquiry.status === 'NEW' && (
            <button
              className={styles.primaryBtn}
              onClick={() => statusMutation.mutate('IN_PROGRESS')}
              disabled={statusMutation.isPending}
            >
              Start Progress
            </button>
          )}
          {['NEW', 'IN_PROGRESS'].includes(enquiry.status) && (
            <>
              <button
                className={styles.primaryBtn}
                style={{ backgroundColor: '#10b981' }}
                onClick={() => {
                  if (window.confirm('Convert to Quotation?')) {
                    convertMutation.mutate();
                  }
                }}
                disabled={convertMutation.isPending || !enquiry.client_id}
                title={!enquiry.client_id ? 'Client must be assigned to convert' : ''}
              >
                Convert to Quotation
              </button>
              <button
                className={styles.primaryBtn}
                style={{ backgroundColor: '#ef4444' }}
                onClick={() => {
                  if (window.confirm('Close this enquiry?')) {
                    statusMutation.mutate('CLOSED');
                  }
                }}
                disabled={statusMutation.isPending}
              >
                Close
              </button>
            </>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '2rem' }}>
        <div>
          {/* Details Section */}
          <div style={{ background: 'white', padding: '1.5rem', borderRadius: '8px', border: '1px solid #e5e7eb', marginBottom: '2rem' }}>
            <h3 style={{ marginTop: 0, marginBottom: '1rem', fontSize: '1.125rem' }}>Enquiry Details</h3>

            {enquiry.items_description && (
              <div style={{ marginBottom: '1.5rem' }}>
                <strong style={{ display: 'block', fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.5rem' }}>
                  Raw Request Description
                </strong>
                <p style={{ margin: 0, whiteSpace: 'pre-wrap', background: '#f9fafb', padding: '1rem', borderRadius: '4px' }}>
                  {enquiry.items_description}
                </p>
              </div>
            )}

            {enquiry.items && enquiry.items.length > 0 && (
              <div>
                <strong style={{ display: 'block', fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.5rem' }}>
                  Structured Items
                </strong>
                <table className={styles.table} style={{ border: '1px solid #e5e7eb', borderRadius: '4px' }}>
                  <thead>
                    <tr>
                      <th>Description</th>
                      <th>Quantity</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {enquiry.items.map((item, i) => (
                      <tr key={i}>
                        <td>{item.description}</td>
                        <td>{item.quantity_requested}</td>
                        <td>{item.notes || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Notes Section */}
          {enquiry.notes && (
            <div style={{ background: 'white', padding: '1.5rem', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
              <h3 style={{ marginTop: 0, marginBottom: '1rem', fontSize: '1.125rem' }}>Internal Notes</h3>
              <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{enquiry.notes}</p>
            </div>
          )}
        </div>

        <div>
          {/* Contact Section */}
          <div style={{ background: 'white', padding: '1.5rem', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
            <h3 style={{ marginTop: 0, marginBottom: '1rem', fontSize: '1.125rem' }}>Contact Info</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div>
                <strong style={{ display: 'block', fontSize: '0.75rem', color: '#6b7280', textTransform: 'uppercase' }}>
                  Client / Contact Name
                </strong>
                {enquiry.client_id ? (
                  <Link to={`/clients/${enquiry.client_id}`} style={{ color: '#3b82f6', textDecoration: 'none' }}>
                    {clientName}
                  </Link>
                ) : (
                  <span>{clientName}</span>
                )}
                {!enquiry.client_id && (
                  <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#ef4444' }}>
                    ⚠️ Unlinked Contact (Cannot Convert)
                  </div>
                )}
              </div>

              {enquiry.contact_phone && (
                <div>
                  <strong style={{ display: 'block', fontSize: '0.75rem', color: '#6b7280', textTransform: 'uppercase' }}>Phone</strong>
                  {enquiry.contact_phone}
                </div>
              )}

              {enquiry.contact_whatsapp && (
                <div>
                  <strong style={{ display: 'block', fontSize: '0.75rem', color: '#6b7280', textTransform: 'uppercase' }}>WhatsApp</strong>
                  {enquiry.contact_whatsapp}
                </div>
              )}

              {enquiry.contact_email && (
                <div>
                  <strong style={{ display: 'block', fontSize: '0.75rem', color: '#6b7280', textTransform: 'uppercase' }}>Email</strong>
                  {enquiry.contact_email}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
