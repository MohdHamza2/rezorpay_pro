import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, LayoutGrid, List } from 'lucide-react';
import { getClients } from '../../api/clients';
import { getEnquiries, type EnquiryRead, type EnquiryStatus } from '../../api/enquiries';
import styles from './Enquiries.module.css';

const STATUSES: EnquiryStatus[] = ['NEW', 'IN_PROGRESS', 'QUOTED', 'CLOSED'];

const StatusBadge = ({ status }: { status: EnquiryStatus }) => {
  const mapping: Record<EnquiryStatus, string> = {
    NEW: styles.badgeNew,
    IN_PROGRESS: styles.badgeInProgress,
    QUOTED: styles.badgeQuoted,
    CLOSED: styles.badgeClosed,
  };
  return <span className={`${styles.badge} ${mapping[status]}`}>{status.replace('_', ' ')}</span>;
};

export const Enquiries = () => {
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<'kanban' | 'list'>('kanban');
  const [status, setStatus] = useState<EnquiryStatus | ''>('');
  const [clientId, setClientId] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const perPage = viewMode === 'kanban' ? 100 : 20;

  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });

  const { data, isLoading } = useQuery({
    queryKey: ['enquiries', { status, clientId, search, page, perPage }],
    queryFn: () =>
      getEnquiries({
        skip: (page - 1) * perPage,
        limit: perPage,
        status: status || undefined,
        client_id: clientId || undefined,
        search: search || undefined,
      }),
  });

  const getClientName = (id?: string | null) => {
    if (!id) return '-';
    const c = clients?.find((c) => c.id === id);
    return c ? c.name : 'Unknown';
  };

  const enquiries = data?.items || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / perPage);

  const renderKanban = () => {
    const columns: Record<EnquiryStatus, EnquiryRead[]> = {
      NEW: [],
      IN_PROGRESS: [],
      QUOTED: [],
      CLOSED: [],
    };
    enquiries.forEach((enq) => {
      if (columns[enq.status]) {
        columns[enq.status].push(enq);
      }
    });

    return (
      <div className={styles.kanbanBoard}>
        {STATUSES.map((colStatus) => (
          <div key={colStatus} className={styles.kanbanColumn}>
            <div className={styles.kanbanColumnHeader}>
              <span>{colStatus.replace('_', ' ')}</span>
              <span className={styles.kanbanCount}>{columns[colStatus].length}</span>
            </div>
            {columns[colStatus].map((enq) => (
              <div key={enq.id} className={styles.kanbanCard} onClick={() => navigate(`/enquiries/${enq.id}`)}>
                <div className={styles.kanbanCardHeader}>
                  <Link
                    to={`/enquiries/${enq.id}`}
                    className={styles.enquiryNumber}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {enq.enquiry_number}
                  </Link>
                  <span className={styles.kanbanSource}>{enq.source}</span>
                </div>
                <div className={styles.kanbanContact}>
                  {enq.client_id ? getClientName(enq.client_id) : enq.contact_name || 'No Contact'}
                </div>
                <div className={styles.kanbanDate}>
                  {new Date(enq.created_at).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  };

  const renderList = () => (
    <div className={styles.tableContainer}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Number</th>
            <th>Date</th>
            <th>Client/Contact</th>
            <th>Source</th>
            <th>Status</th>
            <th className={styles.actions}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {enquiries.map((enq) => (
            <tr key={enq.id}>
              <td>
                <Link to={`/enquiries/${enq.id}`} className={styles.enquiryNumber}>
                  {enq.enquiry_number}
                </Link>
              </td>
              <td>{new Date(enq.created_at).toLocaleDateString()}</td>
              <td>{enq.client_id ? getClientName(enq.client_id) : enq.contact_name || '-'}</td>
              <td>{enq.source}</td>
              <td>
                <StatusBadge status={enq.status} />
              </td>
              <td className={styles.actions}>
                <button
                  className={styles.iconBtn}
                  onClick={() => navigate(`/enquiries/${enq.id}`)}
                  title="View"
                >
                  <Eye size={16} />
                </button>
              </td>
            </tr>
          ))}
          {enquiries.length === 0 && !isLoading && (
            <tr>
              <td colSpan={6} style={{ textAlign: 'center', color: '#6b7280' }}>
                No enquiries found.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className={styles.pagination}>
        <div>
          Showing {enquiries.length > 0 ? (page - 1) * perPage + 1 : 0} to{' '}
          {Math.min(page * perPage, total)} of {total} results
        </div>
        <div className={styles.pageControls}>
          <button
            className={styles.pageBtn}
            disabled={page === 1}
            onClick={() => setPage(p => p - 1)}
          >
            Previous
          </button>
          <span>
            Page {page} of {Math.max(1, totalPages)}
          </span>
          <button
            className={styles.pageBtn}
            disabled={page >= totalPages}
            onClick={() => setPage(p => p + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Enquiries</h2>
      </div>

      <div className={styles.controls}>
        <div className={styles.filters}>
          <div className={styles.filterGroup}>
            <label htmlFor="enquiry-search">Search</label>
            <input
              id="enquiry-search"
              placeholder="Number, Name..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <div className={styles.filterGroup}>
            <label htmlFor="enquiry-status">Status</label>
            <select
              id="enquiry-status"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value as EnquiryStatus | '');
                setPage(1);
              }}
            >
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s.replace('_', ' ')}</option>
              ))}
            </select>
          </div>
          <div className={styles.filterGroup}>
            <label htmlFor="enquiry-client">Client</label>
            <select
              id="enquiry-client"
              value={clientId}
              onChange={(e) => {
                setClientId(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All clients</option>
              {clients?.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className={styles.viewToggle}>
          <button
            className={`${styles.toggleBtn} ${viewMode === 'kanban' ? styles.active : ''}`}
            onClick={() => {
              setViewMode('kanban');
              setPage(1);
            }}
            title="Kanban View"
          >
            <LayoutGrid size={18} />
          </button>
          <button
            className={`${styles.toggleBtn} ${viewMode === 'list' ? styles.active : ''}`}
            onClick={() => {
              setViewMode('list');
              setPage(1);
            }}
            title="List View"
          >
            <List size={18} />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div style={{ padding: '2rem', textAlign: 'center' }}>Loading...</div>
      ) : (
        viewMode === 'kanban' ? renderKanban() : renderList()
      )}
    </div>
  );
};
