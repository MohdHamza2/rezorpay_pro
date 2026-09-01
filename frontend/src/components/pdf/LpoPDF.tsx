import { Document, Page, Text, View, StyleSheet, pdf } from '@react-pdf/renderer';
import type { Client } from '../../api/clients';
import type { CustomerPurchaseOrder, LpoItem } from '../../api/lpos';
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
  colQty: { width: '9%', textAlign: 'right' },
  colInv: { width: '9%', textAlign: 'right' },
  colRem: { width: '10%', textAlign: 'right' },
  colUnit: { width: '12%', textAlign: 'right' },
  colNet: { width: '12%', textAlign: 'right' },
  colRate: { width: '8%', textAlign: 'right' },
  colVat: { width: '8%', textAlign: 'right' },
  colGross: { width: '10%', textAlign: 'right' },
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
      <PdfStackedLabel en={PDF_LABELS.customer.en} ar={PDF_LABELS.customer.ar} boldEn />
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

function LineRow({ item }: { item: LpoItem }) {
  return (
    <View style={styles.tableRow}>
      <View style={styles.colDesc}>
        <Text>{item.description}</Text>
        {item.sku_snapshot ? <Text style={styles.sku}>SKU: {item.sku_snapshot}</Text> : null}
      </View>
      <Text style={styles.colQty}>{item.quantity}</Text>
      <Text style={styles.colInv}>{item.quantity_invoiced}</Text>
      <Text style={styles.colRem}>{item.quantity_remaining}</Text>
      <Text style={styles.colUnit}>{money(item.unit_price)}</Text>
      <Text style={styles.colNet}>{money(item.line_net)}</Text>
      <Text style={styles.colRate}>{money(item.tax_rate)}%</Text>
      <Text style={styles.colVat}>{money(item.tax_amount)}</Text>
      <Text style={styles.colGross}>{money(item.total_price)}</Text>
    </View>
  );
}

export const LpoPDF = ({
  lpo,
  client,
  workspace,
  quotationNumber,
}: {
  lpo: CustomerPurchaseOrder;
  client?: Client;
  workspace?: Workspace;
  quotationNumber?: string;
}) => (
  <Document>
    <Page size="A4" style={styles.page}>
      {lpo.status === 'CANCELLED' ? (
        <PdfWatermark
          en={PDF_LABELS.watermarkCancelled.en}
          ar={PDF_LABELS.watermarkCancelled.ar}
          color="#fca5a5"
        />
      ) : null}
      <View style={styles.header}>
        <SellerBlock workspace={workspace} />
        <View style={styles.headerRight}>
          <View style={styles.statusBadge}>
            <Text>{lpo.status}</Text>
          </View>
        </View>
      </View>
      <PdfDualTitle en={PDF_TITLES.lpo.en} ar={PDF_TITLES.lpo.ar} />

      <View style={styles.metaInfo}>
        <BuyerBlock client={client} />
        <View style={styles.quoteDetails}>
          <View style={styles.detailRow}>
            <PdfStackedLabel en={PDF_LABELS.lpoNo.en} ar={PDF_LABELS.lpoNo.ar} />
            <Text style={styles.detailValue}>{lpo.lpo_number}</Text>
          </View>
          {lpo.customer_po_number ? (
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.customerPo.en} ar={PDF_LABELS.customerPo.ar} />
              <Text style={styles.detailValue}>{lpo.customer_po_number}</Text>
            </View>
          ) : null}
          {quotationNumber ? (
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.quoteNo.en} ar={PDF_LABELS.quoteNo.ar} />
              <Text style={styles.detailValue}>{quotationNumber}</Text>
            </View>
          ) : null}
          <View style={styles.detailRow}>
            <PdfStackedLabel en={PDF_LABELS.lpoDate.en} ar={PDF_LABELS.lpoDate.ar} />
            <Text style={styles.detailValue}>{lpo.lpo_date}</Text>
          </View>
          {lpo.expected_delivery_date ? (
            <View style={styles.detailRow}>
              <PdfStackedLabel
                en={PDF_LABELS.expectedDelivery.en}
                ar={PDF_LABELS.expectedDelivery.ar}
              />
              <Text style={styles.detailValue}>{lpo.expected_delivery_date}</Text>
            </View>
          ) : null}
          <View style={styles.detailRow}>
            <PdfStackedLabel en={PDF_LABELS.currency.en} ar={PDF_LABELS.currency.ar} />
            <Text style={styles.detailValue}>AED</Text>
          </View>
        </View>
      </View>

      <View style={styles.table}>
        <View style={styles.tableHeader}>
          <PdfHeadCell style={styles.colDesc} en={PDF_LABELS.description.en} ar={PDF_LABELS.description.ar} />
          <PdfHeadCell style={styles.colQty} en={PDF_LABELS.ordered.en} ar={PDF_LABELS.ordered.ar} />
          <PdfHeadCell style={styles.colInv} en={PDF_LABELS.invoiced.en} ar={PDF_LABELS.invoiced.ar} />
          <PdfHeadCell style={styles.colRem} en={PDF_LABELS.remain.en} ar={PDF_LABELS.remain.ar} />
          <PdfHeadCell style={styles.colUnit} en={PDF_LABELS.unit.en} ar={PDF_LABELS.unit.ar} />
          <PdfHeadCell style={styles.colNet} en={PDF_LABELS.net.en} ar={PDF_LABELS.net.ar} />
          <PdfHeadCell style={styles.colRate} en={PDF_LABELS.vatPercent.en} ar={PDF_LABELS.vatPercent.ar} />
          <PdfHeadCell style={styles.colVat} en="VAT" ar={PDF_LABELS.vatAed.ar} />
          <PdfHeadCell style={styles.colGross} en={PDF_LABELS.gross.en} ar={PDF_LABELS.gross.ar} />
        </View>
        {(lpo.items ?? []).map((item, index) => (
          <LineRow key={item.id || index} item={item} />
        ))}
      </View>

      <View style={styles.summary}>
        <View style={styles.summaryRow}>
          <PdfStackedLabel en={PDF_LABELS.subtotalExclVat.en} ar={PDF_LABELS.subtotalExclVat.ar} />
          <Text>AED {money(lpo.subtotal)}</Text>
        </View>
        <View style={styles.summaryRow}>
          <PdfStackedLabel en={PDF_LABELS.vat.en} ar={PDF_LABELS.vat.ar} />
          <Text>AED {money(lpo.tax_amount)}</Text>
        </View>
        <View style={styles.summaryTotal}>
          <PdfStackedLabel en={PDF_LABELS.totalAed.en} ar={PDF_LABELS.totalAed.ar} boldEn />
          <Text>{money(lpo.total_amount)}</Text>
        </View>
      </View>

      {lpo.notes ? (
        <View style={styles.notes}>
          <PdfStackedLabel en={PDF_LABELS.notes.en} ar={PDF_LABELS.notes.ar} />
          <Text>{lpo.notes}</Text>
        </View>
      ) : null}

      <PdfBilingualFooter />
    </Page>
  </Document>
);

export async function downloadLpoPdf(args: {
  lpo: CustomerPurchaseOrder;
  client?: Client;
  workspace?: Workspace;
  quotationNumber?: string;
}): Promise<void> {
  registerPdfFonts();
  const blob = await pdf(
    <LpoPDF
      lpo={args.lpo}
      client={args.client}
      workspace={args.workspace}
      quotationNumber={args.quotationNumber}
    />,
  ).toBlob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `LPO_${args.lpo.lpo_number}.pdf`;
  anchor.click();
  URL.revokeObjectURL(url);
}
