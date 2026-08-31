import { Document, Page, Text, View, StyleSheet, pdf } from '@react-pdf/renderer';
import type { Client } from '../../api/clients';
import type { DeliveryNote, DeliveryNoteItem } from '../../api/deliveryNotes';
import type { Workspace } from '../../api/workspaces';

function formatQty(value: string | number | null | undefined): string {
  return Number(value ?? 0).toFixed(2);
}

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
  quoteDetails: { width: '44%' },
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
  sku: { color: '#6b7280', fontSize: 7, marginTop: 1 },
  notes: { marginTop: 16, color: '#4b5563', maxWidth: '70%' },
  footer: {
    position: 'absolute',
    bottom: 24,
    left: 28,
    right: 28,
    borderTop: '1px solid #e5e7eb',
    paddingTop: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    color: '#6b7280',
    fontSize: 8,
  },
  statusBadge: {
    padding: '4 8',
    borderRadius: 4,
    color: 'white',
    backgroundColor: '#2563eb',
    alignSelf: 'flex-end',
    marginTop: 8,
    fontSize: 9,
  },
  watermark: {
    position: 'absolute',
    top: '42%',
    left: 0,
    right: 0,
    textAlign: 'center',
    fontSize: 48,
    color: '#fca5a5',
    opacity: 0.35,
    letterSpacing: 6,
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
      {trn ? <Text style={styles.companyDetails}>TRN: {trn}</Text> : null}
    </View>
  );
}

function BuyerBlock({ client }: { client?: Client }) {
  const name = (client?.name ?? '').trim();
  const address = (client?.address ?? '').trim();
  const trn = (client?.tax_id ?? '').trim();
  return (
    <View style={styles.clientSection}>
      <Text style={styles.clientTitle}>DELIVER TO:</Text>
      <Text style={styles.clientName}>{name || 'Valued Customer'}</Text>
      {address ? <Text style={styles.companyDetails}>{address}</Text> : null}
      {trn ? <Text style={styles.companyDetails}>TRN: {trn}</Text> : null}
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
}) => {
  const watermark = dn.status === 'CANCELLED' ? 'CANCELLED' : null;
  return (
    <Document>
      <Page size="A4" style={styles.page}>
        {watermark ? <Text style={styles.watermark}>{watermark}</Text> : null}
        <View style={styles.header}>
          <SellerBlock workspace={workspace} />
          <View style={styles.headerRight}>
            <Text style={styles.title}>Delivery Note</Text>
            <View style={styles.statusBadge}>
              <Text>{dn.status}</Text>
            </View>
          </View>
        </View>

        <View style={styles.metaInfo}>
          <BuyerBlock client={client} />
          <View style={styles.quoteDetails}>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>DN No:</Text>
              <Text style={styles.detailValue}>{dn.dn_number}</Text>
            </View>
            {lpoNumber ? (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>LPO No:</Text>
                <Text style={styles.detailValue}>{lpoNumber}</Text>
              </View>
            ) : null}
            {invoiceNumber ? (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Invoice No:</Text>
                <Text style={styles.detailValue}>{invoiceNumber}</Text>
              </View>
            ) : null}
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Delivery Date:</Text>
              <Text style={styles.detailValue}>{dn.delivery_date}</Text>
            </View>
            {dn.vehicle_number ? (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Vehicle:</Text>
                <Text style={styles.detailValue}>{dn.vehicle_number}</Text>
              </View>
            ) : null}
            {dn.driver_name ? (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Driver:</Text>
                <Text style={styles.detailValue}>{dn.driver_name}</Text>
              </View>
            ) : null}
          </View>
        </View>

        <View style={styles.table}>
          <View style={styles.tableHeader}>
            <Text style={styles.colSku}>SKU</Text>
            <Text style={styles.colDesc}>Description</Text>
            <Text style={styles.colQty}>Qty</Text>
          </View>
          {(dn.items ?? []).map((item, index) => (
            <LineRow key={item.id || index} item={item} />
          ))}
        </View>

        {dn.shipping_address ? (
          <View style={styles.notes}>
            <Text style={styles.detailLabel}>Shipping address</Text>
            <Text>{dn.shipping_address}</Text>
          </View>
        ) : null}

        {dn.notes ? (
          <View style={styles.notes}>
            <Text style={styles.detailLabel}>Notes</Text>
            <Text>{dn.notes}</Text>
          </View>
        ) : null}

        <View style={styles.footer}>
          <Text>Delivery Note — not a tax invoice. Quantities only.</Text>
          <Text>Generated by InvoiceSaaS</Text>
        </View>
      </Page>
    </Document>
  );
};

export async function downloadDeliveryNotePdf(args: {
  dn: DeliveryNote;
  client?: Client;
  workspace?: Workspace;
  lpoNumber?: string;
  invoiceNumber?: string;
}): Promise<void> {
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
