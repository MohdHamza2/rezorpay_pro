import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import {
  getArAgingSummary,
  getArAgingDetail,
  getArAgingByCustomer,
  getApAgingSummary,
  getApAgingDetail,
  getApAgingBySupplier,
  downloadVatComplianceZip,
  getVatComplianceJson,
  exportStatementBlob,
  type ArAgingSummary,
  type ArAgingByCustomer,
  type ArAgingDetail,
  type ArAgingDetailRow,
  type ApAgingSummary,
  type ApAgingBySupplier,
  type ApAgingDetail,
  type ApAgingDetailRow,
  type CreditBuckets,
  BUCKET_LABELS,
  formatAed,
} from '../api/reports';
import {
  getRevenue,
  getSalesByCustomer,
  getSalesByProduct,
  getCashflow,
  type AnalyticsInterval,
  type CashflowReport,
  type RevenueRow,
  type SalesByCustomerRow,
  type SalesByProductRow,
} from '../api/analytics';
import { useAuth } from '../contexts/AuthContext';
import { Skeleton } from '../components/Skeleton';
import { defaultStatementRange } from './statementHelpers';
import {
  Download,
  FileJson,
  FileArchive,
  Building2,
  Copy,
  Users,
  User,
  BarChart3,
  FileText,
  FileSpreadsheet,
  ChevronDown,
} from 'lucide-react';
import styles from './Reports.module.css';

const toLocalIso = (): string => {
  return new Date().toISOString().slice(0, 10);
};

const MAX_VAT_PERIOD_DAYS = 366;

const saveBlob = (blob: Blob, filename: string): void => {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
};

const bucketChartData = (buckets?: CreditBuckets) =>
  BUCKET_LABELS.map(({ key, label }) => ({
    name: label,
    value: buckets ? buckets[key] : 0,
  }));

interface DetailRow {
  id: string;
  entityName: string;
  number: string;
  due_date: string;
  days_overdue: number;
  balance_due: number;
  bucket: string;
}

const toDetailRows = (rows: (ArAgingDetailRow | ApAgingDetailRow)[]): DetailRow[] =>
  rows.map((row) => {
    if ('client_name' in row) {
      const r = row as ArAgingDetailRow;
      return {
        id: r.invoice_id,
        entityName: r.client_name,
        number: r.invoice_number,
        due_date: r.due_date,
        days_overdue: r.days_overdue,
        balance_due: r.balance_due,
        bucket: r.bucket,
      };
    }
    const r = row as ApAgingDetailRow;
    return {
      id: r.supplier_invoice_id,
      entityName: r.supplier_name,
      number: r.supplier_invoice_number,
      due_date: r.due_date,
      days_overdue: r.days_overdue,
      balance_due: r.balance_due,
      bucket: r.bucket,
    };
  });

interface AgingTabProps {
  side: 'ar' | 'ap';
}

const AgingTab = ({ side }: AgingTabProps) => {
  const isAr = side === 'ar';
  const [asOf, setAsOf] = useState<string>(toLocalIso());
  const [historical, setHistorical] = useState(false);
  const [selectedRow, setSelectedRow] = useState<{ id: string; name: string } | null>(null);
  const [showAllDetail, setShowAllDetail] = useState(false);
  const [openStmtFor, setOpenStmtFor] = useState<string | null>(null);
  const [exportingFmt, setExportingFmt] = useState<'pdf' | 'csv' | null>(null);

  const summary = useQuery<ArAgingSummary | ApAgingSummary>({
    queryKey: ['reports', side, 'summary', asOf, historical],
    queryFn: async () =>
      isAr ? getArAgingSummary(asOf, undefined, historical) : getApAgingSummary(asOf),
  });

  const byEntity = useQuery<ArAgingByCustomer | ApAgingBySupplier>({
    queryKey: ['reports', side, 'by-entity', asOf, historical],
    queryFn: async () =>
      isAr
        ? getArAgingByCustomer(asOf, historical)
        : getApAgingBySupplier(asOf),
  });

  const detail = useQuery<ArAgingDetail | ApAgingDetail>({
    queryKey: ['reports', side, 'detail', asOf, historical, selectedRow?.id, showAllDetail],
    queryFn: async () =>
      isAr
        ? getArAgingDetail(asOf, selectedRow?.id, historical)
        : getApAgingDetail(asOf, selectedRow?.id),
    enabled: showAllDetail || selectedRow !== null,
  });

  const today = toLocalIso();
  const asOfInvalid = asOf > today;

  const summaryData = summary.data as ArAgingSummary & ApAgingSummary | undefined;
  const byEntityData = byEntity.data as ArAgingByCustomer & ApAgingBySupplier | undefined;
  const detailData = detail.data as (ArAgingDetail & ApAgingDetail) | undefined;

  const entityCols = isAr
    ? ((byEntityData as ArAgingByCustomer | undefined)?.customers ?? []).map((row) => ({
        id: row.client.id,
        name: row.client.name,
        total: row.total_outstanding,
        buckets: row.buckets,
        pdc_outstanding_count: row.pdc_outstanding_count ?? 0,
        pdc_outstanding_amount: row.pdc_outstanding_amount ?? 0,
        // AR has no landed cost (D-22 is AP-side only) — always 0
        landed_cost_outstanding_count: 0,
        landed_cost_outstanding_amount: 0,
      }))
    : ((byEntityData as ApAgingBySupplier | undefined)?.suppliers ?? []).map((row) => ({
        id: row.supplier.id,
        name: row.supplier.name,
        total: row.total_outstanding,
        buckets: row.buckets,
        pdc_outstanding_count: row.pdc_outstanding_count ?? 0,
        pdc_outstanding_amount: row.pdc_outstanding_amount ?? 0,
        landed_cost_outstanding_count: row.landed_cost_outstanding_count ?? 0,
        landed_cost_outstanding_amount: row.landed_cost_outstanding_amount ?? 0,
      }));

  const closeDetail = () => {
    setSelectedRow(null);
    setShowAllDetail(false);
  };

  useEffect(() => {
    if (!openStmtFor) return;
    const close = () => setOpenStmtFor(null);
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, [openStmtFor]);

  const handleExport = async (id: string, fmt: 'pdf' | 'csv') => {
    if (exportingFmt) return;
    const range = defaultStatementRange();
    setExportingFmt(fmt);
    try {
      const blob = await exportStatementBlob(
        isAr ? 'ar' : 'ap',
        id,
        range.from,
        range.to,
        range.as_of,
        fmt
      );
      saveBlob(
        blob,
        `${isAr ? 'ar-statement' : 'ap-statement'}-${id}-${range.from}_to_${range.to}.${fmt}`
      );
      setOpenStmtFor(null);
    } catch {
      // interceptor already surfaces the error toast
    } finally {
      setExportingFmt(null);
    }
  };

  if (summary.isLoading || byEntity.isLoading) {
    return (
      <div className={styles.tabBody}>
        <Skeleton height="120px" />
        <Skeleton height="320px" />
      </div>
    );
  }

  const title = isAr ? 'Receivables (AR) Aging' : 'Payables (AP) Aging';
  const balanceLabel = isAr ? 'outstanding receivables' : 'outstanding payables';

  return (
    <div className={styles.tabBody}>
      <div className={styles.reportHeader}>
        <h2>{title}</h2>
        <div className={styles.filterRow}>
          <label className={styles.field}>
            <span>As of</span>
            <input
              type="date"
              value={asOf}
              max={today}
              onChange={(e) => setAsOf(e.target.value)}
            />
          </label>
          {asOfInvalid && <span className={styles.errorText}>As-of cannot be in the future.</span>}
          {isAr && (
            <label
              className={styles.checkField}
              title="Historical balance reconstruction: rebuilds balances from payment/credit-note history as of the selected date. Balances only — lifecycle status is not reconstructed."
            >
              <input
                type="checkbox"
                checked={historical}
                onChange={(e) => setHistorical(e.target.checked)}
              />
              <span>Historical balance reconstruction</span>
            </label>
          )}
          <button
            className={styles.linkBtn}
            onClick={() => (showAllDetail ? closeDetail() : setShowAllDetail(true))}
          >
            {showAllDetail ? 'Hide detail' : 'All detail'}
          </button>
        </div>
      </div>

      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Total {balanceLabel}</span>
          <span className={styles.statValue} data-testid={isAr ? 'report-ar-total' : 'report-ap-total'}>
            AED {formatAed(summaryData?.total_outstanding ?? 0)}
          </span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Open {isAr ? 'invoices' : 'supplier invoices'}</span>
          <span className={styles.statValue}>{summaryData?.invoice_count ?? 0}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>{isAr ? 'Customers' : 'Suppliers'}</span>
          <span className={styles.statValue}>
            {isAr ? summaryData?.client_count ?? 0 : summaryData?.supplier_count ?? 0}
          </span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>{isAr ? 'AR PDC Outstanding' : 'AP PDC Outstanding'}</span>
          <span className={styles.statValue}>
            AED {formatAed(summaryData?.pdc_outstanding_amount ?? 0)}
          </span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>PDC Instruments</span>
          <span className={styles.statValue}>{summaryData?.pdc_outstanding_count ?? 0}</span>
        </div>
      </div>

      <div className={styles.chartCard}>
        <h3>Bucket distribution</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={bucketChartData(summaryData?.buckets)}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip formatter={(value) => `AED ${formatAed(Number(value))}`} />
            <Bar dataKey="value" fill="#2563eb" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className={styles.entityTable}>
        <h3>{isAr ? 'By customer' : 'By supplier'}</h3>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>{isAr ? 'Customer' : 'Supplier'}</th>
              <th className={styles.num}>Total</th>
              {BUCKET_LABELS.map(({ key, label }) => (
                <th key={key} className={styles.num}>
                  {label}
                </th>
              ))}
              <th className={styles.num}>PDC Count</th>
              <th className={styles.num}>PDC Amount</th>
              {!isAr && (
                <>
                  <th className={styles.num}>LC Count</th>
                  <th className={styles.num}>LC Amount</th>
                </>
              )}
              <th></th>
            </tr>
          </thead>
          <tbody>
            {entityCols.map((row) => (
              <tr
                key={row.id}
                className={selectedRow?.id === row.id ? styles.activeRow : undefined}
                data-testid={
                  isAr ? `report-ar-customer-row-${row.id}` : `report-ap-supplier-row-${row.id}`
                }
              >
                <td>
                  {isAr ? <Users size={16} /> : <Building2 size={16} />}
                  <span className={styles.entityName}>{row.name}</span>
                </td>
                <td className={styles.num}>{formatAed(row.total)}</td>
                {BUCKET_LABELS.map(({ key }) => (
                  <td key={key} className={styles.num}>
                    {formatAed(row.buckets[key])}
                  </td>
                ))}
                <td className={styles.num}>{row.pdc_outstanding_count ?? 0}</td>
                <td className={styles.num}>
                  AED {formatAed(row.pdc_outstanding_amount ?? 0)}
                </td>
                {!isAr && (
                  <>
                    <td className={styles.num}>{row.landed_cost_outstanding_count ?? 0}</td>
                    <td className={styles.num}>
                      AED {formatAed(row.landed_cost_outstanding_amount ?? 0)}
                    </td>
                  </>
                )}
                <td className={styles.entityCells}>
                  <button
                    className={styles.linkBtn}
                    onClick={() =>
                      selectedRow?.id === row.id
                        ? setSelectedRow(null)
                        : setSelectedRow({ id: row.id, name: row.name })
                    }
                  >
                    {selectedRow?.id === row.id ? 'Hide detail' : 'View detail'}
                  </button>
                  <div className={styles.stmtWrap} onClick={(e) => e.stopPropagation()}>
                    {openStmtFor === row.id ? (
                      <div className={styles.stmtMenu}>
                        <button
                          className={styles.stmtMenuItem}
                          disabled={exportingFmt !== null}
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleExport(row.id, 'pdf');
                          }}
                        >
                          <FileText size={14} />
                          {exportingFmt === 'pdf' ? 'Downloading…' : 'Statement PDF'}
                        </button>
                        <button
                          className={styles.stmtMenuItem}
                          disabled={exportingFmt !== null}
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleExport(row.id, 'csv');
                          }}
                        >
                          <FileSpreadsheet size={14} />
                          {exportingFmt === 'csv' ? 'Downloading…' : 'Statement CSV'}
                        </button>
                      </div>
                    ) : (
                      <button
                        className={styles.linkBtn}
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpenStmtFor(row.id);
                        }}
                      >
                        Statement <ChevronDown size={14} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {entityCols.length === 0 && (
              <tr>
                <td colSpan={BUCKET_LABELS.length + 3} className={styles.emptyCell}>
                  No open {isAr ? 'receivables' : 'payables'} for this as-of date.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {(showAllDetail || selectedRow) && (
        <div className={styles.detailBlock}>
          <div className={styles.detailHeader}>
            <h3>
              Invoice detail
              {selectedRow ? ` — ${selectedRow.name}` : ''}
            </h3>
            <span className={styles.muted}>
              {detailData?.invoices.length ?? 0} invoice(s), total AED{' '}
              {formatAed(detailData?.total_outstanding ?? 0)}
            </span>
          </div>
          {detail.isLoading ? (
            <Skeleton height="180px" />
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Due date</th>
                  <th className={styles.num}>Days overdue</th>
                  <th className={styles.num}>Balance</th>
                  <th>Bucket</th>
                </tr>
              </thead>
              <tbody>
                {toDetailRows(detailData?.invoices ?? []).map((row) => (
                  <tr key={row.id}>
                    <td>
                      <span className={styles.entityName}>{row.number}</span>
                      <span className={styles.muted}> · {row.entityName}</span>
                    </td>
                    <td>{row.due_date}</td>
                    <td className={styles.num}>{row.days_overdue}</td>
                    <td className={styles.num}>{formatAed(row.balance_due)}</td>
                    <td>{row.bucket.replaceAll('_', ' ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};

const VatTab = () => {
  const { user } = useAuth();
  const canManageVat = user?.role === 'OWNER' || user?.role === 'ADMIN';
  const today = toLocalIso();
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [busy, setBusy] = useState<'zip' | 'json' | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  const vatInvalid =
    from !== '' && to !== '' && (from > to || from > today || to > today);
  const periodTooLong =
    from !== '' && to !== '' && !vatInvalid && !(from > to);
  const days =
    periodTooLong && from && to
      ? Math.round((new Date(to).getTime() - new Date(from).getTime()) / 86400000)
      : 0;
  const periodError = periodTooLong && days > MAX_VAT_PERIOD_DAYS;

  const handleZip = async () => {
    if (!from || !to || !canManageVat) return;
    setBusy('zip');
    try {
      const blob = await downloadVatComplianceZip(from, to);
      saveBlob(blob, `vat-compliance-${from}_to_${to}.zip`);
    } catch {
      // interceptor already surfaces the error toast
    } finally {
      setBusy(null);
    }
  };

  const handleJsonDownload = async () => {
    if (!from || !to || !canManageVat) return;
    setBusy('json');
    try {
      const data = await getVatComplianceJson(from, to);
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json',
      });
      saveBlob(blob, `vat-compliance-${from}_to_${to}.json`);
    } catch {
      // interceptor already surfaces the error toast
    } finally {
      setBusy(null);
    }
  };

  const handlePreview = async () => {
    if (!from || !to || !canManageVat) return;
    if (preview) {
      setPreview(null);
      return;
    }
    setBusy('json');
    try {
      const data = await getVatComplianceJson(from, to);
      setPreview(
        JSON.stringify(
          {
            period: { from: data.manifest.period.from, to: data.manifest.period.to },
            org: data.manifest.org,
            currency: data.manifest.currency,
            summary: data.manifest.summary,
            files: data.manifest.files,
            warnings: data.manifest.warnings,
            counts: {
              sales_invoices: data.sales_invoices.length,
              invoice_lines: data.invoice_lines.length,
              credit_notes: data.credit_notes.length,
              tax_debit_notes: data.tax_debit_notes.length,
              purchase_invoices: data.purchase_invoices.length,
            },
          },
          null,
          2
        )
      );
    } catch {
      // interceptor already surfaces the error toast
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={styles.tabBody}>
      <div className={styles.reportHeader}>
        <h2>UAE VAT Compliance Pack</h2>
        <div className={styles.filterRow}>
          <label className={styles.field}>
            <span>From</span>
            <input type="date" value={from} max={today} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className={styles.field}>
            <span>To</span>
            <input type="date" value={to} max={today} onChange={(e) => setTo(e.target.value)} />
          </label>
        </div>
      </div>

      {vatInvalid && (
        <p className={styles.errorText}>Dates must be within today and satisfy from ≤ to.</p>
      )}
      {periodError && (
        <p className={styles.errorText}>Period cannot exceed {MAX_VAT_PERIOD_DAYS} days.</p>
      )}

      {!canManageVat && (
        <div className={styles.notice}>
          <h3>OWNER/ADMIN only</h3>
          <p>The VAT compliance export (CSV ZIP and JSON) is restricted to workspace owners and admins.</p>
        </div>
      )}

      <div className={styles.vatPanel}>
        <button
          className={styles.actionBtn}
          disabled={!canManageVat || !from || !to || vatInvalid || periodError || busy !== null}
          onClick={handleZip}
        >
          <FileArchive size={18} /> {busy === 'zip' ? 'Preparing…' : 'Download CSV ZIP'}
        </button>
        <button
          className={styles.actionBtn}
          disabled={!canManageVat || !from || !to || vatInvalid || periodError || busy !== null}
          onClick={handleJsonDownload}
        >
          <Download size={18} /> {busy === 'json' ? 'Preparing…' : 'Download JSON'}
        </button>
        <button
          className={styles.actionBtn}
          disabled={!canManageVat || !from || !to || vatInvalid || periodError || busy !== null}
          onClick={handlePreview}
        >
          <FileJson size={18} /> {preview ? 'Hide preview' : 'Preview JSON'} <Copy size={14} />
        </button>
      </div>

      {preview && (
        <div className={styles.previewBlock}>
          <pre className={styles.preview} data-testid="report-vat-preview">
            {preview}
          </pre>
        </div>
      )}
    </div>
  );
};

const INTERVALS: ReadonlyArray<{ value: AnalyticsInterval; label: string }> = [
  { value: 'day', label: 'Daily' },
  { value: 'week', label: 'Weekly' },
  { value: 'month', label: 'Monthly' },
];

interface BarDatum {
  name: string;
  [key: string]: string | number;
}

const barData = <T extends { period: string }>(
  rows: T[] | undefined,
  key: (row: T) => number
): BarDatum[] =>
  (rows ?? []).map((row) => ({ name: row.period, value: key(row) }));

const BarChartBox = ({ data }: { data: BarDatum[] }) =>
  data.length === 0 ? (
    <div className={styles.emptyCell}>No data for this period.</div>
  ) : (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" />
        <YAxis />
        <Tooltip formatter={(value) => `AED ${formatAed(Number(value))}`} />
        <Bar dataKey="value" fill="#2563eb" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );

const ChartSection = ({
  loading,
  error,
  data,
}: {
  loading: boolean;
  error: boolean;
  data: BarDatum[];
}) =>
  loading ? (
    <Skeleton height="260px" />
  ) : error ? (
    <div className={styles.errorText}>Failed to load analytics. Try again.</div>
  ) : (
    <BarChartBox data={data} />
  );

const AnalyticsTab = () => {
  const { user } = useAuth();
  const canView = user?.role === 'OWNER' || user?.role === 'ADMIN';
  const today = toLocalIso();
  const [from, setFrom] = useState<string>(toLocalIso());
  const [to, setTo] = useState<string>(today);
  const [interval, setInterval] = useState<AnalyticsInterval>('month');

  const periodInvalid = from !== '' && to !== '' && (from > to || from > today || to > today);
  const ready = canView && from !== '' && to !== '' && !periodInvalid;

  const revenue = useQuery<RevenueRow[]>({
    queryKey: ['analytics', 'revenue', from, to, interval],
    queryFn: async () => {
      const data = await getRevenue(from, to, interval);
      return data.rows;
    },
    enabled: ready,
  });

  const byCustomer = useQuery<SalesByCustomerRow[]>({
    queryKey: ['analytics', 'by-customer', from, to],
    queryFn: async () => {
      const data = await getSalesByCustomer(from, to);
      return data.rows;
    },
    enabled: ready,
  });

  const byProduct = useQuery<SalesByProductRow[]>({
    queryKey: ['analytics', 'by-product', from, to],
    queryFn: async () => {
      const data = await getSalesByProduct(from, to);
      return data.rows;
    },
    enabled: ready,
  });

  const cashflow = useQuery<CashflowReport>({
    queryKey: ['analytics', 'cashflow', from, to, interval],
    queryFn: () => getCashflow(from, to, interval),
    enabled: ready,
  });

  if (!periodInvalid && !canView) {
    return (
      <div className={styles.tabBody}>
        <div className={styles.notice}>
          <h3>OWNER/ADMIN only</h3>
          <p>
            Analytics reports (revenue, cashflow, sales by customer/product) are restricted to
            workspace owners and admins.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.tabBody}>
      <div className={styles.reportHeader}>
        <h2>Analytics</h2>
        <div className={styles.filterRow}>
          <label className={styles.field}>
            <span>From</span>
            <input type="date" value={from} max={today} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className={styles.field}>
            <span>To</span>
            <input type="date" value={to} max={today} onChange={(e) => setTo(e.target.value)} />
          </label>
          <label className={styles.field}>
            <span>Interval</span>
            <select
              value={interval}
              onChange={(e) => setInterval(e.target.value as AnalyticsInterval)}
            >
              {INTERVALS.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {periodInvalid && (
        <p className={styles.errorText}>
          Period must be within today and satisfy from ≤ to.
        </p>
      )}

      <div className={styles.chartCard}>
        <h3>Revenue</h3>
        <ChartSection
          loading={revenue.isLoading}
          error={revenue.isError}
          data={barData(revenue.data, (r) => r.total_amount)}
        />
      </div>

      <div className={styles.chartCard}>
        <h3>Cashflow (net)</h3>
        <ChartSection
          loading={cashflow.isLoading}
          error={cashflow.isError}
          data={barData(cashflow.data?.rows, (r) => r.net)}
        />
        {!!cashflow.data && cashflow.data.non_aed_payments_excluded > 0 && (
          <p className={styles.warningText}>
            {cashflow.data.non_aed_payments_excluded} non-AED supplier payment
            {cashflow.data.non_aed_payments_excluded === 1 ? '' : 's'} excluded from AED
            cashflow.
          </p>
        )}
      </div>

      <div className={styles.entityTable}>
        <h3>Sales by customer</h3>
        {byCustomer.isLoading ? (
          <Skeleton height="160px" />
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Customer</th>
                <th className={styles.num}>Invoices</th>
                <th className={styles.num}>Subtotal</th>
                <th className={styles.num}>Tax</th>
                <th className={styles.num}>Total</th>
              </tr>
            </thead>
            <tbody>
              {byCustomer.data?.map((row) => (
                <tr key={row.client_id}>
                  <td>
                    <Users size={16} />
                    <span className={styles.entityName}>{row.client_name}</span>
                  </td>
                  <td className={styles.num}>{row.invoice_count}</td>
                  <td className={styles.num}>{formatAed(row.subtotal)}</td>
                  <td className={styles.num}>{formatAed(row.tax_amount)}</td>
                  <td className={styles.num}>{formatAed(row.total_amount)}</td>
                </tr>
              ))}
              {byCustomer.data?.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    No invoiced sales in this period.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <div className={styles.entityTable}>
        <h3>Sales by product</h3>
        {byProduct.isLoading ? (
          <Skeleton height="160px" />
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Product</th>
                <th>SKU</th>
                <th className={styles.num}>Qty</th>
                <th className={styles.num}>Net</th>
                <th className={styles.num}>Tax</th>
                <th className={styles.num}>Total</th>
              </tr>
            </thead>
            <tbody>
              {byProduct.data?.map((row) => (
                <tr key={row.sku}>
                  <td>
                    <span className={styles.entityName}>{row.product_name}</span>
                  </td>
                  <td>{row.sku}</td>
                  <td className={styles.num}>{row.quantity}</td>
                  <td className={styles.num}>{formatAed(row.line_net)}</td>
                  <td className={styles.num}>{formatAed(row.tax_amount)}</td>
                  <td className={styles.num}>{formatAed(row.total_price)}</td>
                </tr>
              ))}
              {byProduct.data?.length === 0 && (
                <tr>
                  <td colSpan={6} className={styles.emptyCell}>
                    No invoiced line items in this period.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export const Reports = () => {
  const [tab, setTab] = useState<'ar' | 'ap' | 'vat' | 'analytics'>('ar');

  return (
    <div className={styles.container}>
      <h1 className={styles.title}>Reports</h1>
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${tab === 'ar' ? styles.activeTab : ''}`}
          onClick={() => setTab('ar')}
        >
          <User size={16} /> AR Aging
        </button>
        <button
          className={`${styles.tab} ${tab === 'ap' ? styles.activeTab : ''}`}
          onClick={() => setTab('ap')}
        >
          <Building2 size={16} /> AP Aging
        </button>
        <button
          className={`${styles.tab} ${tab === 'vat' ? styles.activeTab : ''}`}
          onClick={() => setTab('vat')}
        >
          <FileArchive size={16} /> VAT Compliance
        </button>
        <button
          className={`${styles.tab} ${tab === 'analytics' ? styles.activeTab : ''}`}
          onClick={() => setTab('analytics')}
        >
          <BarChart3 size={16} /> Analytics
        </button>
      </div>

      {tab === 'ar' && <AgingTab side="ar" />}
      {tab === 'ap' && <AgingTab side="ap" />}
      {tab === 'vat' && <VatTab />}
      {tab === 'analytics' && <AnalyticsTab />}
    </div>
  );
};
