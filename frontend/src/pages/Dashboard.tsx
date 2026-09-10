import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getDashboardStats } from '../api/dashboard';
import { getRecentInvoices } from '../api/invoices';
import { getArAgingSummary, getApAgingSummary } from '../api/reports';
import { Skeleton } from '../components/Skeleton';
import {
  DollarSign,
  ShoppingCart,
  SendToBack,
  ClipboardCheck,
  TrendingUp,
  FileText,
  Receipt,
  Building2,
  User,
  ArrowRight,
  Banknote,
} from 'lucide-react';
import styles from './Dashboard.module.css';

export const Dashboard = () => {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['dashboard_stats'],
    queryFn: getDashboardStats,
  });

  const { data: recentInvoices, isLoading: invoicesLoading } = useQuery({
    queryKey: ['dashboard_recent_invoices'],
    queryFn: getRecentInvoices,
  });

  const { data: arSummary } = useQuery({
    queryKey: ['dashboard_ar_summary'],
    queryFn: () => getArAgingSummary(),
  });

  const { data: apSummary } = useQuery({
    queryKey: ['dashboard_ap_summary'],
    queryFn: () => getApAgingSummary(),
  });

  const formatAed = (v: number) =>
    v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

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
          <div className={styles.statValue} data-testid="dash-total-receivables">
            AED {formatAed(stats?.outstanding_balance ?? 0)}
          </div>
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
          <div className={styles.statValue} data-testid="dash-pending-prs">{stats?.pending_prs} PRs</div>
          <div className={styles.statTrend} style={{ color: '#4b5563' }}>
            Awaiting review &amp; approval
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statLabel}>Active Market Sourcing</span>
            <SendToBack className={styles.statIcon} style={{ color: '#d97706' }} size={20} />
          </div>
          <div className={styles.statValue} data-testid="dash-active-rfqs">{stats?.active_rfqs} RFQs</div>
          <div className={styles.statTrend} style={{ color: '#4b5563' }}>
            Awaiting supplier quotes
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statLabel}>Pending Inbound QA</span>
            <ClipboardCheck className={styles.statIcon} style={{ color: '#dc2626' }} size={20} />
          </div>
          <div className={styles.statValue} data-testid="dash-pending-grns">{stats?.unposted_grns} GRNs</div>
          <div className={styles.statTrend} style={{ color: '#4b5563' }}>
            Stock awaiting inspection &amp; posting
          </div>
        </div>
      </div>

      <div className={styles.widgetContainer}>
        <div className={styles.widget}>
          <h3>
            <Receipt size={18} style={{ verticalAlign: 'middle', marginRight: 6 }} />
            Recent Invoices
          </h3>
          {invoicesLoading ? (
            <Skeleton height="140px" />
          ) : (recentInvoices ?? []).length === 0 ? (
            <p className={styles.muted}>No invoices yet.</p>
          ) : (
            <ul className={styles.invoiceList} data-testid="dash-recent-invoices">
              {recentInvoices!.map((inv) => (
                <li
                  key={inv.id}
                  className={styles.invoiceRow}
                  data-testid={`dash-recent-invoice-${inv.id}`}
                >
                  <div className={styles.invoiceMain}>
                    <span className={styles.invoiceNumber}>{inv.invoice_number}</span>
                    <span className={styles.invoiceDate}>{inv.issue_date}</span>
                  </div>
                  <div className={styles.invoiceMeta}>
                    <span className={styles.invoiceStatus}>{inv.status}</span>
                    <span className={styles.invoiceBalance}>AED {formatAed(inv.balance_due)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <Link to="/invoices" className={styles.viewAllLink}>
            View all invoices <ArrowRight size={14} />
          </Link>
        </div>

        <div className={styles.widget}>
          <h3>
            <Banknote size={18} style={{ verticalAlign: 'middle', marginRight: 6 }} />
            Open AR / AP
          </h3>
          <div className={styles.snapshotGrid}>
            <Link to="/reports" className={styles.snapshotItem}>
              <span className={styles.snapshotLabel}>
                <User size={16} /> AR (receivables)
              </span>
              <span className={styles.snapshotValue} data-testid="dash-ar-snapshot">
                AED {formatAed(arSummary?.total_outstanding ?? 0)}
              </span>
              <span className={styles.snapshotCount}>
                {arSummary?.invoice_count ?? 0} invoice(s), {arSummary?.client_count ?? 0} customer(s)
              </span>
            </Link>
            <Link to="/reports" className={styles.snapshotItem}>
              <span className={styles.snapshotLabel}>
                <Building2 size={16} /> AP (payables)
              </span>
              <span className={styles.snapshotValue} data-testid="dash-ap-snapshot">
                AED {formatAed(apSummary?.total_outstanding ?? 0)}
              </span>
              <span className={styles.snapshotCount}>
                {apSummary?.invoice_count ?? 0} invoice(s), {apSummary?.supplier_count ?? 0} supplier(s)
              </span>
            </Link>
          </div>
        </div>
      </div>

      <div className={styles.widgetContainer}>
        <div className={styles.widget}>
          <h3>Quick Actions</h3>
          <div className={styles.actionsGrid}>
            <Link to="/invoices?new=1" className={styles.quickActionBtn}>
              <FileText size={16} /> Create Invoice
            </Link>
            <Link to="/procurement" className={styles.quickActionBtn}>
              <ShoppingCart size={16} /> Log Procurement Request
            </Link>
            <Link to="/grn" className={styles.quickActionBtn}>
              <ClipboardCheck size={16} /> Record Goods Receipt
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};
