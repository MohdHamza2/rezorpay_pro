import { Document, Page, Text, View, StyleSheet, pdf } from '@react-pdf/renderer';
import type { ArStatement, ArStatementLine, ArStatementParty } from '../../api/clients';
import {
  AGING_ROWS,
  OUTSTANDING_COPY,
  PDC_SUCCESS_NOTE,
  formatMoney,
  isPendingLine,
} from '../../pages/statementHelpers';
import { PdfDualTitle } from './PdfDualTitle';
import {
  agingBucketAr,
  PdfArText,
  PdfBilingualFooter,
  PdfHeadCell,
  PdfStackedLabel,
  PdfTrnLine,
  statementTypeAr,
} from './pdfChrome';
import { registerPdfFonts } from './pdfFonts';
import { PDF_LABELS } from './pdfLabels';
import { PDF_TITLES } from './pdfTitles';

registerPdfFonts();

const styles = StyleSheet.create({
  page: { padding: 28, fontSize: 9, fontFamily: 'Helvetica' },
  header: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 12 },
  headerLeft: { flexDirection: 'column', maxWidth: '58%' },
  companyName: { fontSize: 14, fontWeight: 'bold' },
  companyDetails: { color: '#4b5563', marginTop: 3, lineHeight: 1.35 },
  metaInfo: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 18 },
  clientSection: { flexDirection: 'column', width: '52%' },
  clientName: { fontSize: 12, fontWeight: 'bold', color: '#111827' },
  details: { width: '44%' },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 3,
    borderBottom: '1px solid #f3f4f6',
  },
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
  agingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 3,
    borderBottom: '1px solid #f3f4f6',
  },
  notes: { marginTop: 16, color: '#6b7280', fontSize: 8, lineHeight: 1.4 },
});

function SellerBlock({ workspace }: { workspace: ArStatementParty }) {
  return (
    <View style={styles.headerLeft}>
      <Text style={styles.companyName}>{workspace.name || 'Your Company LLC'}</Text>
      {workspace.address ? <Text style={styles.companyDetails}>{workspace.address}</Text> : null}
      {workspace.trn ? (
        <View style={styles.companyDetails}>
          <PdfTrnLine digits={workspace.trn} />
        </View>
      ) : null}
    </View>
  );
}

function BuyerBlock({ client }: { client: ArStatementParty }) {
  return (
    <View style={styles.clientSection}>
      <PdfStackedLabel en={PDF_LABELS.client.en} ar={PDF_LABELS.client.ar} boldEn />
      <Text style={styles.clientName}>{client.name || 'Valued Customer'}</Text>
      {client.address ? <Text style={styles.companyDetails}>{client.address}</Text> : null}
      {client.tax_id ? (
        <View style={styles.companyDetails}>
          <PdfTrnLine digits={client.tax_id} />
        </View>
      ) : null}
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
        <PdfArText>{statementTypeAr(line.doc_type)}</PdfArText>
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
        <PdfStackedLabel en={PDF_LABELS.billed.en} ar={PDF_LABELS.billed.ar} />
        <Text>AED {formatMoney(data.totals.billed)}</Text>
      </View>
      <View style={styles.summaryRow}>
        <PdfStackedLabel en={PDF_LABELS.paidSuccess.en} ar={PDF_LABELS.paidSuccess.ar} />
        <Text>AED {formatMoney(data.totals.paid)}</Text>
      </View>
      <View style={styles.summaryRow}>
        <PdfStackedLabel
          en={PDF_LABELS.creditedTaxCreditNotes.en}
          ar={PDF_LABELS.creditedTaxCreditNotes.ar}
        />
        <Text>AED {formatMoney(data.totals.credited)}</Text>
      </View>
      <View style={styles.summaryTotal}>
        <PdfStackedLabel en={PDF_LABELS.amountDueNow.en} ar={PDF_LABELS.amountDueNow.ar} boldEn />
        <Text>AED {formatMoney(data.amount_due_now)}</Text>
      </View>
      <View style={styles.summaryRow}>
        <PdfStackedLabel en={PDF_LABELS.unappliedCredit.en} ar={PDF_LABELS.unappliedCredit.ar} />
        <Text>AED {formatMoney(data.credit_balance)}</Text>
      </View>
    </View>
  );
}

function AgingBlock({ data }: { data: ArStatement }) {
  return (
    <View style={styles.aging}>
      <PdfStackedLabel en={PDF_LABELS.aging.en} ar={PDF_LABELS.aging.ar} boldEn />
      {AGING_ROWS.map((row) => (
        <View key={row.key} style={styles.agingRow}>
          <PdfStackedLabel en={row.label} ar={agingBucketAr(row.key)} />
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
      </View>
      <PdfDualTitle en={PDF_TITLES.accountStatement.en} ar={PDF_TITLES.accountStatement.ar} />

      <View style={styles.metaInfo}>
        <BuyerBlock client={data.client} />
        <View style={styles.details}>
          <View style={styles.detailRow}>
            <PdfStackedLabel en={PDF_LABELS.period.en} ar={PDF_LABELS.period.ar} />
            <Text style={styles.detailValue}>
              {data.from}–{data.to}
            </Text>
          </View>
          <View style={styles.detailRow}>
            <PdfStackedLabel en={PDF_LABELS.asOf.en} ar={PDF_LABELS.asOf.ar} />
            <Text style={styles.detailValue}>{data.as_of}</Text>
          </View>
          <View style={styles.detailRow}>
            <PdfStackedLabel en={PDF_LABELS.currency.en} ar={PDF_LABELS.currency.ar} />
            <Text style={styles.detailValue}>{data.currency || 'AED'}</Text>
          </View>
        </View>
      </View>

      <View style={styles.table}>
        <View style={styles.tableHeader} wrap={false} fixed>
          <PdfHeadCell style={styles.colDate} en={PDF_LABELS.date.en} ar={PDF_LABELS.date.ar} />
          <PdfHeadCell style={styles.colType} en={PDF_LABELS.type.en} ar={PDF_LABELS.type.ar} />
          <PdfHeadCell style={styles.colNumber} en={PDF_LABELS.number.en} ar={PDF_LABELS.number.ar} />
          <PdfHeadCell style={styles.colDebit} en={PDF_LABELS.debit.en} ar={PDF_LABELS.debit.ar} />
          <PdfHeadCell style={styles.colCredit} en={PDF_LABELS.credit.en} ar={PDF_LABELS.credit.ar} />
          <PdfHeadCell style={styles.colBalance} en={PDF_LABELS.balance.en} ar={PDF_LABELS.balance.ar} />
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

      <PdfBilingualFooter flow />
    </Page>
  </Document>
);

function fileSlug(name: string): string {
  return name.replace(/[^\w-]+/g, '_').slice(0, 40) || 'client';
}

export async function downloadStatementPdf(data: ArStatement): Promise<void> {
  registerPdfFonts();
  const blob = await pdf(<StatementPDF data={data} />).toBlob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `AccountStatement_${fileSlug(data.client.name)}_${data.from}_${data.to}.pdf`;
  anchor.click();
  URL.revokeObjectURL(url);
}
