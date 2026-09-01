import { Document, Page, Text, View, StyleSheet, pdf } from '@react-pdf/renderer';
import type { ArStatement, ArStatementLine, ArStatementParty } from '../../api/clients';
import {
  AGING_ROWS,
  OUTSTANDING_COPY,
  PDC_SUCCESS_NOTE,
  formatMoney,
  isPendingLine,
} from '../../pages/statementHelpers';

const styles = StyleSheet.create({
  page: { padding: 28, fontSize: 9, fontFamily: 'Helvetica' },
  header: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 20 },
  headerLeft: { flexDirection: 'column', maxWidth: '58%' },
  headerRight: { flexDirection: 'column', alignItems: 'flex-end' },
  title: { fontSize: 20, fontWeight: 'bold', color: '#111827' },
  companyName: { fontSize: 14, fontWeight: 'bold' },
  companyDetails: { color: '#4b5563', marginTop: 3, lineHeight: 1.35 },
  metaInfo: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 18 },
  clientSection: { flexDirection: 'column', width: '52%' },
  clientTitle: { fontSize: 9, fontWeight: 'bold', color: '#6b7280', marginBottom: 4 },
  clientName: { fontSize: 12, fontWeight: 'bold', color: '#111827' },
  details: { width: '44%' },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 3,
    borderBottom: '1px solid #f3f4f6',
  },
  detailLabel: { color: '#6b7280' },
  detailValue: { fontWeight: 'bold' },
  table: { width: '100%', marginTop: 12 },
  tableHeader: {
    flexDirection: 'row',
    backgroundColor: '#f9fafb',
    paddingVertical: 6,
    paddingHorizontal: 4,
    borderBottom: '1px solid #e5e7eb',
    fontWeight: 'bold',
    fontSize: 7,
  },
  tableRow: {
    flexDirection: 'row',
    paddingVertical: 5,
    paddingHorizontal: 4,
    borderBottom: '1px solid #e5e7eb',
    fontSize: 8,
  },
  colDate: { width: '14%' },
  colType: { width: '24%' },
  colNumber: { width: '16%' },
  colDebit: { width: '15%', textAlign: 'right' },
  colCredit: { width: '15%', textAlign: 'right' },
  colBalance: { width: '16%', textAlign: 'right' },
  sku: { color: '#6b7280', fontSize: 7, marginTop: 1 },
  summary: { width: '48%', alignSelf: 'flex-end', marginTop: 16 },
  summaryRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3 },
  summaryTotal: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 7,
    borderTop: '2px solid #e5e7eb',
    marginTop: 4,
    fontWeight: 'bold',
    fontSize: 11,
  },
  aging: { marginTop: 16, width: '52%' },
  agingTitle: { fontSize: 9, fontWeight: 'bold', marginBottom: 6, color: '#111827' },
  agingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 3,
    borderBottom: '1px solid #f3f4f6',
  },
  notes: { marginTop: 16, color: '#6b7280', fontSize: 8, lineHeight: 1.4 },
  footer: {
    marginTop: 18,
    borderTop: '1px solid #e5e7eb',
    paddingTop: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    color: '#6b7280',
    fontSize: 8,
  },
});

function SellerBlock({ workspace }: { workspace: ArStatementParty }) {
  return (
    <View style={styles.headerLeft}>
      <Text style={styles.companyName}>{workspace.name || 'Your Company LLC'}</Text>
      {workspace.address ? <Text style={styles.companyDetails}>{workspace.address}</Text> : null}
      {workspace.trn ? <Text style={styles.companyDetails}>TRN: {workspace.trn}</Text> : null}
    </View>
  );
}

function BuyerBlock({ client }: { client: ArStatementParty }) {
  return (
    <View style={styles.clientSection}>
      <Text style={styles.clientTitle}>CLIENT:</Text>
      <Text style={styles.clientName}>{client.name || 'Valued Customer'}</Text>
      {client.address ? <Text style={styles.companyDetails}>{client.address}</Text> : null}
      {client.tax_id ? <Text style={styles.companyDetails}>TRN: {client.tax_id}</Text> : null}
    </View>
  );
}

function typeSecondLine(line: ArStatementLine): string | null {
  if (line.payment_method) return line.payment_method;
  if (isPendingLine(line.doc_type)) return 'not cleared';
  return null;
}

function creditAmount(line: ArStatementLine): string {
  if (isPendingLine(line.doc_type)) return formatMoney(0);
  return formatMoney(line.credit);
}

function LineRow({ line }: { line: ArStatementLine }) {
  const extra = typeSecondLine(line);
  return (
    <View style={styles.tableRow} wrap={false}>
      <Text style={styles.colDate}>{line.date}</Text>
      <View style={styles.colType}>
        <Text>{line.doc_type_label}</Text>
        {extra ? <Text style={styles.sku}>{extra}</Text> : null}
      </View>
      <View style={styles.colNumber}>
        <Text>{line.number || '—'}</Text>
        {line.reference ? <Text style={styles.sku}>{line.reference}</Text> : null}
      </View>
      <Text style={styles.colDebit}>{formatMoney(line.debit)}</Text>
      <Text style={styles.colCredit}>{creditAmount(line)}</Text>
      <Text style={styles.colBalance}>{formatMoney(line.running_balance)}</Text>
    </View>
  );
}

function TotalsBlock({ data }: { data: ArStatement }) {
  return (
    <View style={styles.summary}>
      <View style={styles.summaryRow}>
        <Text style={styles.detailLabel}>Billed:</Text>
        <Text>AED {formatMoney(data.totals.billed)}</Text>
      </View>
      <View style={styles.summaryRow}>
        <Text style={styles.detailLabel}>Paid (SUCCESS):</Text>
        <Text>AED {formatMoney(data.totals.paid)}</Text>
      </View>
      <View style={styles.summaryRow}>
        <Text style={styles.detailLabel}>Credited (tax credit notes):</Text>
        <Text>AED {formatMoney(data.totals.credited)}</Text>
      </View>
      <View style={styles.summaryTotal}>
        <Text>Amount due now:</Text>
        <Text>AED {formatMoney(data.amount_due_now)}</Text>
      </View>
      <View style={styles.summaryRow}>
        <Text style={styles.detailLabel}>Unapplied credit:</Text>
        <Text>AED {formatMoney(data.credit_balance)}</Text>
      </View>
    </View>
  );
}

function AgingBlock({ data }: { data: ArStatement }) {
  return (
    <View style={styles.aging}>
      <Text style={styles.agingTitle}>Aging</Text>
      {AGING_ROWS.map((row) => (
        <View key={row.key} style={styles.agingRow}>
          <Text style={styles.detailLabel}>{row.label}</Text>
          <Text>AED {formatMoney(data.aging.buckets[row.key])}</Text>
        </View>
      ))}
    </View>
  );
}

export const StatementPDF = ({ data }: { data: ArStatement }) => (
  <Document title="Account Statement">
    <Page size="A4" style={styles.page} wrap>
      <View style={styles.header}>
        <SellerBlock workspace={data.workspace} />
        <View style={styles.headerRight}>
          <Text
            style={styles.title}
            id="statement-pdf-title"
            {...({ 'data-testid': 'statement-pdf-title' } as { id?: string })}
          >
            Account Statement
          </Text>
        </View>
      </View>

      <View style={styles.metaInfo}>
        <BuyerBlock client={data.client} />
        <View style={styles.details}>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Period:</Text>
            <Text style={styles.detailValue}>
              {data.from}–{data.to}
            </Text>
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>As of:</Text>
            <Text style={styles.detailValue}>{data.as_of}</Text>
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Currency:</Text>
            <Text style={styles.detailValue}>{data.currency || 'AED'}</Text>
          </View>
        </View>
      </View>

      <View style={styles.table}>
        <View style={styles.tableHeader} wrap={false} fixed>
          <Text style={styles.colDate}>Date</Text>
          <Text style={styles.colType}>Type</Text>
          <Text style={styles.colNumber}>Number</Text>
          <Text style={styles.colDebit}>Debit</Text>
          <Text style={styles.colCredit}>Credit</Text>
          <Text style={styles.colBalance}>Balance</Text>
        </View>
        {data.lines.map((line, index) => (
          <LineRow key={`${line.doc_type}-${line.number ?? index}`} line={line} />
        ))}
      </View>

      <TotalsBlock data={data} />
      <AgingBlock data={data} />

      <View style={styles.notes}>
        <Text>{OUTSTANDING_COPY}</Text>
        <Text>{PDC_SUCCESS_NOTE}</Text>
      </View>

      <View style={styles.footer}>
        <Text>Account Statement — amounts in AED. English only.</Text>
        <Text>Generated by InvoiceSaaS</Text>
      </View>
    </Page>
  </Document>
);

function fileSlug(name: string): string {
  return name.replace(/[^\w-]+/g, '_').slice(0, 40) || 'client';
}

export async function downloadStatementPdf(data: ArStatement): Promise<void> {
  const blob = await pdf(<StatementPDF data={data} />).toBlob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `AccountStatement_${fileSlug(data.client.name)}_${data.from}_${data.to}.pdf`;
  anchor.click();
  URL.revokeObjectURL(url);
}
