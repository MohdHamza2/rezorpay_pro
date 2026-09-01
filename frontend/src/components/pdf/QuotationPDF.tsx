import { Document, Page, Text, View, StyleSheet, pdf } from '@react-pdf/renderer';
import type { Client } from '../../api/clients';
import type { Quotation, QuotationItem } from '../../api/quotations';
import type { Workspace } from '../../api/workspaces';
import { PdfDualTitle } from './PdfDualTitle';
import {
  PdfBilingualFooter,
  PdfHeadCell,
  PdfStackedLabel,
  PdfTrnLine,
  PdfWatermark,
} from './pdfChrome';
import { registerPdfFonts } from './pdfFonts';
import { PDF_LABELS } from './pdfLabels';
import { PDF_TITLES } from './pdfTitles';

registerPdfFonts();

const styles = StyleSheet.create({
  page: { padding: 28, fontSize: 9, fontFamily: 'Helvetica' },
  header: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 12 },
  headerLeft: { flexDirection: 'column', maxWidth: '58%' },
  headerRight: { flexDirection: 'column', alignItems: 'flex-end' },
  companyName: { fontSize: 14, fontWeight: 'bold' },
  companyDetails: { color: '#4b5563', marginTop: 3, lineHeight: 1.35 },
  metaInfo: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 18 },
  clientSection: { flexDirection: 'column', width: '52%' },
  clientName: { fontSize: 12, fontWeight: 'bold', color: '#111827' },
  quoteDetails: { width: '44%' },
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
  colDesc: { width: '22%' },
  colQty: { width: '8%', textAlign: 'right' },
  colUnit: { width: '12%', textAlign: 'right' },
  colDisc: { width: '10%', textAlign: 'right' },
  colNet: { width: '12%', textAlign: 'right' },
  colRate: { width: '8%', textAlign: 'right' },
  colVat: { width: '12%', textAlign: 'right' },
  colGross: { width: '16%', textAlign: 'right' },
  sku: { color: '#6b7280', fontSize: 7, marginTop: 1 },
  summary: { width: '42%', alignSelf: 'flex-end', marginTop: 16 },
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
  notes: { marginTop: 16, color: '#4b5563', maxWidth: '55%' },
  statusBadge: {
    padding: '4 8',
    borderRadius: 4,
    color: 'white',
    backgroundColor: '#2563eb',
    alignSelf: 'flex-end',
    fontSize: 9,
  },
});

function money(value: string | number | null | undefined): string {
  return Number(value ?? 0).toFixed(2);
}

function discountLabel(item: QuotationItem): string {
  const pct = Number(item.discount_percent ?? 0);
  const amt = Number(item.discount_amount ?? 0);
  if (pct > 0) return `${money(pct)}%`;
  if (amt > 0) return money(amt);
  return '—';
}

function quoteWatermark(status: Quotation['status']) {
  if (status === 'EXPIRED') return PDF_LABELS.watermarkExpired;
  if (status === 'REJECTED') return PDF_LABELS.watermarkRejected;
  return null;
}

function SellerBlock({ workspace }: { workspace?: Workspace }) {
  const name = (workspace?.name ?? '').trim();
  const address = (workspace?.address ?? '').trim();
  const trn = (workspace?.trn ?? '').trim();
  return (
    <View style={styles.headerLeft}>
      <Text style={styles.companyName}>{name || 'Your Company LLC'}</Text>
      {address ? <Text style={styles.companyDetails}>{address}</Text> : null}
      {trn ? (
        <View style={styles.companyDetails}>
          <PdfTrnLine digits={trn} />
        </View>
      ) : null}
    </View>
  );
}

function BuyerBlock({ client }: { client?: Client }) {
  const name = (client?.name ?? '').trim();
  const address = (client?.address ?? '').trim();
  const trn = (client?.tax_id ?? '').trim();
  return (
    <View style={styles.clientSection}>
      <PdfStackedLabel en={PDF_LABELS.quoteTo.en} ar={PDF_LABELS.quoteTo.ar} boldEn />
      <Text style={styles.clientName}>{name || 'Valued Customer'}</Text>
      {address ? <Text style={styles.companyDetails}>{address}</Text> : null}
      {trn ? (
        <View style={styles.companyDetails}>
          <PdfTrnLine digits={trn} />
        </View>
      ) : null}
      {client?.email ? <Text style={styles.companyDetails}>{client.email}</Text> : null}
    </View>
  );
}

function LineRow({ item }: { item: QuotationItem }) {
  return (
    <View style={styles.tableRow}>
      <View style={styles.colDesc}>
        <Text>{item.description}</Text>
        {item.sku_snapshot ? <Text style={styles.sku}>SKU: {item.sku_snapshot}</Text> : null}
      </View>
      <Text style={styles.colQty}>{item.quantity}</Text>
      <Text style={styles.colUnit}>{money(item.unit_price)}</Text>
      <Text style={styles.colDisc}>{discountLabel(item)}</Text>
      <Text style={styles.colNet}>{money(item.line_net)}</Text>
      <Text style={styles.colRate}>{money(item.tax_rate)}%</Text>
      <Text style={styles.colVat}>{money(item.tax_amount)}</Text>
      <Text style={styles.colGross}>{money(item.total_price)}</Text>
    </View>
  );
}

export const QuotationPDF = ({
  quotation,
  client,
  workspace,
}: {
  quotation: Quotation;
  client?: Client;
  workspace?: Workspace;
}) => {
  const mark = quoteWatermark(quotation.status);
  return (
    <Document>
      <Page size="A4" style={styles.page}>
        {mark ? <PdfWatermark en={mark.en} ar={mark.ar} color="#fca5a5" /> : null}
        <View style={styles.header}>
          <SellerBlock workspace={workspace} />
          <View style={styles.headerRight}>
            <View style={styles.statusBadge}>
              <Text>{quotation.status}</Text>
            </View>
          </View>
        </View>
        <PdfDualTitle en={PDF_TITLES.quotation.en} ar={PDF_TITLES.quotation.ar} />

        <View style={styles.metaInfo}>
          <BuyerBlock client={client} />
          <View style={styles.quoteDetails}>
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.quoteNo.en} ar={PDF_LABELS.quoteNo.ar} />
              <Text style={styles.detailValue}>{quotation.quotation_number}</Text>
            </View>
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.quotationDate.en} ar={PDF_LABELS.quotationDate.ar} />
              <Text style={styles.detailValue}>{quotation.quotation_date}</Text>
            </View>
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.validUntil.en} ar={PDF_LABELS.validUntil.ar} />
              <Text style={styles.detailValue}>{quotation.valid_until}</Text>
            </View>
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.currency.en} ar={PDF_LABELS.currency.ar} />
              <Text style={styles.detailValue}>AED</Text>
            </View>
          </View>
        </View>

        <View style={styles.table}>
          <View style={styles.tableHeader}>
            <PdfHeadCell style={styles.colDesc} en={PDF_LABELS.description.en} ar={PDF_LABELS.description.ar} />
            <PdfHeadCell style={styles.colQty} en={PDF_LABELS.qty.en} ar={PDF_LABELS.qty.ar} />
            <PdfHeadCell style={styles.colUnit} en={PDF_LABELS.unit.en} ar={PDF_LABELS.unit.ar} />
            <PdfHeadCell style={styles.colDisc} en={PDF_LABELS.disc.en} ar={PDF_LABELS.disc.ar} />
            <PdfHeadCell style={styles.colNet} en={PDF_LABELS.net.en} ar={PDF_LABELS.net.ar} />
            <PdfHeadCell style={styles.colRate} en={PDF_LABELS.vatPercent.en} ar={PDF_LABELS.vatPercent.ar} />
            <PdfHeadCell style={styles.colVat} en={PDF_LABELS.vatAed.en} ar={PDF_LABELS.vatAed.ar} />
            <PdfHeadCell style={styles.colGross} en={PDF_LABELS.gross.en} ar={PDF_LABELS.gross.ar} />
          </View>
          {(quotation.items ?? []).map((item, index) => (
            <LineRow key={item.id || index} item={item} />
          ))}
        </View>

        <View style={styles.summary}>
          <View style={styles.summaryRow}>
            <PdfStackedLabel en={PDF_LABELS.subtotalExclVat.en} ar={PDF_LABELS.subtotalExclVat.ar} />
            <Text>AED {money(quotation.subtotal)}</Text>
          </View>
          <View style={styles.summaryRow}>
            <PdfStackedLabel en={PDF_LABELS.vat.en} ar={PDF_LABELS.vat.ar} />
            <Text>AED {money(quotation.tax_amount)}</Text>
          </View>
          <View style={styles.summaryTotal}>
            <PdfStackedLabel en={PDF_LABELS.totalAed.en} ar={PDF_LABELS.totalAed.ar} boldEn />
            <Text>{money(quotation.total_amount)}</Text>
          </View>
        </View>

        {quotation.notes ? (
          <View style={styles.notes}>
            <PdfStackedLabel en={PDF_LABELS.notes.en} ar={PDF_LABELS.notes.ar} />
            <Text>{quotation.notes}</Text>
          </View>
        ) : null}

        <PdfBilingualFooter />
      </Page>
    </Document>
  );
};

export async function downloadQuotationPdf(args: {
  quotation: Quotation;
  client?: Client;
  workspace?: Workspace;
}): Promise<void> {
  registerPdfFonts();
  const blob = await pdf(
    <QuotationPDF
      quotation={args.quotation}
      client={args.client}
      workspace={args.workspace}
    />,
  ).toBlob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `Quotation_${args.quotation.quotation_number}.pdf`;
  anchor.click();
  URL.revokeObjectURL(url);
}
