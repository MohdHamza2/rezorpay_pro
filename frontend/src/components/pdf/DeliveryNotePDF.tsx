import { Document, Page, Text, View, StyleSheet, pdf } from '@react-pdf/renderer';
import type { Client } from '../../api/clients';
import type { DeliveryNote, DeliveryNoteItem } from '../../api/deliveryNotes';
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

function formatQty(value: string | number | null | undefined): string {
  return Number(value ?? 0).toFixed(2);
}

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
    fontSize: 8,
  },
  tableRow: {
    flexDirection: 'row',
    paddingVertical: 5,
    paddingHorizontal: 4,
    borderBottom: '1px solid #e5e7eb',
    fontSize: 9,
  },
  colSku: { width: '22%' },
  colDesc: { width: '58%' },
  colQty: { width: '20%', textAlign: 'right' },
  notes: { marginTop: 16, color: '#4b5563', maxWidth: '70%' },
  statusBadge: {
    padding: '4 8',
    borderRadius: 4,
    color: 'white',
    backgroundColor: '#2563eb',
    alignSelf: 'flex-end',
    fontSize: 9,
  },
});

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
      <PdfStackedLabel en={PDF_LABELS.deliverTo.en} ar={PDF_LABELS.deliverTo.ar} boldEn />
      <Text style={styles.clientName}>{name || 'Valued Customer'}</Text>
      {address ? <Text style={styles.companyDetails}>{address}</Text> : null}
      {trn ? (
        <View style={styles.companyDetails}>
          <PdfTrnLine digits={trn} />
        </View>
      ) : null}
    </View>
  );
}

function LineRow({ item }: { item: DeliveryNoteItem }) {
  return (
    <View style={styles.tableRow}>
      <Text style={styles.colSku}>{item.sku_snapshot || '—'}</Text>
      <Text style={styles.colDesc}>{item.description}</Text>
      <Text style={styles.colQty}>{formatQty(item.quantity)}</Text>
    </View>
  );
}

export const DeliveryNotePDF = ({
  dn,
  client,
  workspace,
  lpoNumber,
  invoiceNumber,
}: {
  dn: DeliveryNote;
  client?: Client;
  workspace?: Workspace;
  lpoNumber?: string;
  invoiceNumber?: string;
}) => (
  <Document>
    <Page size="A4" style={styles.page}>
      {dn.status === 'CANCELLED' ? (
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
            <Text>{dn.status}</Text>
          </View>
        </View>
      </View>
      <PdfDualTitle en={PDF_TITLES.deliveryNote.en} ar={PDF_TITLES.deliveryNote.ar} />

      <View style={styles.metaInfo}>
        <BuyerBlock client={client} />
        <View style={styles.quoteDetails}>
          <View style={styles.detailRow}>
            <PdfStackedLabel en={PDF_LABELS.dnNo.en} ar={PDF_LABELS.dnNo.ar} />
            <Text style={styles.detailValue}>{dn.dn_number}</Text>
          </View>
          {lpoNumber ? (
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.lpoNo.en} ar={PDF_LABELS.lpoNo.ar} />
              <Text style={styles.detailValue}>{lpoNumber}</Text>
            </View>
          ) : null}
          {invoiceNumber ? (
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.invoiceNo.en} ar={PDF_LABELS.invoiceNo.ar} />
              <Text style={styles.detailValue}>{invoiceNumber}</Text>
            </View>
          ) : null}
          <View style={styles.detailRow}>
            <PdfStackedLabel en={PDF_LABELS.deliveryDate.en} ar={PDF_LABELS.deliveryDate.ar} />
            <Text style={styles.detailValue}>{dn.delivery_date}</Text>
          </View>
          {dn.vehicle_number ? (
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.vehicle.en} ar={PDF_LABELS.vehicle.ar} />
              <Text style={styles.detailValue}>{dn.vehicle_number}</Text>
            </View>
          ) : null}
          {dn.driver_name ? (
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.driver.en} ar={PDF_LABELS.driver.ar} />
              <Text style={styles.detailValue}>{dn.driver_name}</Text>
            </View>
          ) : null}
        </View>
      </View>

      <View style={styles.table}>
        <View style={styles.tableHeader}>
          <PdfHeadCell style={styles.colSku} en={PDF_LABELS.sku.en} ar={PDF_LABELS.sku.ar} />
          <PdfHeadCell style={styles.colDesc} en={PDF_LABELS.description.en} ar={PDF_LABELS.description.ar} />
          <PdfHeadCell style={styles.colQty} en={PDF_LABELS.qty.en} ar={PDF_LABELS.qty.ar} />
        </View>
        {(dn.items ?? []).map((item, index) => (
          <LineRow key={item.id || index} item={item} />
        ))}
      </View>

      {dn.shipping_address ? (
        <View style={styles.notes}>
          <PdfStackedLabel en={PDF_LABELS.shippingAddress.en} ar={PDF_LABELS.shippingAddress.ar} />
          <Text>{dn.shipping_address}</Text>
        </View>
      ) : null}

      {dn.notes ? (
        <View style={styles.notes}>
          <PdfStackedLabel en={PDF_LABELS.notes.en} ar={PDF_LABELS.notes.ar} />
          <Text>{dn.notes}</Text>
        </View>
      ) : null}

      <PdfBilingualFooter />
    </Page>
  </Document>
);

export async function downloadDeliveryNotePdf(args: {
  dn: DeliveryNote;
  client?: Client;
  workspace?: Workspace;
  lpoNumber?: string;
  invoiceNumber?: string;
}): Promise<void> {
  registerPdfFonts();
  const blob = await pdf(
    <DeliveryNotePDF
      dn={args.dn}
      client={args.client}
      workspace={args.workspace}
      lpoNumber={args.lpoNumber}
      invoiceNumber={args.invoiceNumber}
    />,
  ).toBlob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `DeliveryNote_${args.dn.dn_number}.pdf`;
  anchor.click();
  URL.revokeObjectURL(url);
}
