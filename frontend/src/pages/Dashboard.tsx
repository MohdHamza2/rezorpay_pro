import { useQuery } from '@tanstack/react-query';
import { getDashboardStats } from '../api/dashboard';
import { Skeleton } from '../components/Skeleton';
import { DollarSign, ShoppingCart, SendToBack, ClipboardCheck, TrendingUp } from 'lucide-react';
import styles from './Dashboard.module.css';

export const Dashboard = () => {
  const { data: stats, isLoading } = useQuery({ queryKey: ['dashboard_stats'], queryFn: getDashboardStats });

  if (isLoading) {
    return (
      <div className={styles.container}>
        <h1 className={styles.title}>Overview</h1>
        <div className={styles.statsGrid}>
          <Skeleton height="120px" />
          <Skeleton height="120px" />
          <Skeleton height="120px" />
          <Skeleton height="120px" />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <h1 className={styles.title}>Operations Overview</h1>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statLabel}>Total Receivables (AED)</span>
            <DollarSign className={styles.statIcon} style={{ color: '#059669' }} size={20} />
          </div>
          <div className={styles.statValue}>AED {stats?.outstanding_balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}</div>
          <div className={styles.statTrend}>
            <TrendingUp size={14} style={{ marginRight: 4 }} />
            Across {stats?.total_invoices} active invoices
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statLabel}>Pending Internal Demand</span>
            <ShoppingCart className={styles.statIcon} style={{ color: '#2563eb' }} size={20} />
          </div>
          <div className={styles.statValue}>{stats?.pending_prs} PRs</div>
          <div className={styles.statTrend} style={{ color: '#4b5563' }}>Awaiting review & approval</div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statLabel}>Active Market Sourcing</span>
            <SendToBack className={styles.statIcon} style={{ color: '#d97706' }} size={20} />
          </div>
          <div className={styles.statValue}>{stats?.active_rfqs} RFQs</div>
          <div className={styles.statTrend} style={{ color: '#4b5563' }}>Awaiting supplier quotes</div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statLabel}>Pending Inbound QA</span>
            <ClipboardCheck className={styles.statIcon} style={{ color: '#dc2626' }} size={20} />
          </div>
          <div className={styles.statValue}>{stats?.unposted_grns} GRNs</div>
          <div className={styles.statTrend} style={{ color: '#4b5563' }}>Stock awaiting inspection & posting</div>
        </div>
      </div>
      
      <div className={styles.widgetContainer}>
        <div className={styles.widget}>
          <h3>Recent Activities</h3>
          <p style={{ color: '#6b7280', marginTop: '1rem' }}>No recent activity to display.</p>
        </div>
        <div className={styles.widget}>
          <h3>Quick Actions</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '1rem' }}>
            <button className={styles.quickActionBtn}>Create Customer Invoice</button>
            <button className={styles.quickActionBtn}>Log Procurement Request</button>
            <button className={styles.quickActionBtn}>Record Goods Receipt</button>
          </div>
        </div>
      </div>
    </div>
  );
};
