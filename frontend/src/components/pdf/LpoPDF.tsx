import { Document, Page, Text, View, StyleSheet, pdf } from '@react-pdf/renderer';
import type { Client } from '../../api/clients';
import type { CustomerPurchaseOrder, LpoItem } from '../../api/lpos';
import type { Workspace } from '../../api/workspaces';

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
      <Text style={styles.clientTitle}>CUSTOMER:</Text>
      <Text style={styles.clientName}>{name || 'Valued Customer'}</Text>
      {address ? <Text style={styles.companyDetails}>{address}</Text> : null}
      {trn ? <Text style={styles.companyDetails}>TRN: {trn}</Text> : null}
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
}) => {
  const watermark = lpo.status === 'CANCELLED' ? 'CANCELLED' : null;
  return (
    <Document>
      <Page size="A4" style={styles.page}>
        {watermark ? <Text style={styles.watermark}>{watermark}</Text> : null}
        <View style={styles.header}>
          <SellerBlock workspace={workspace} />
          <View style={styles.headerRight}>
            <Text style={styles.title}>LPO</Text>
            <View style={styles.statusBadge}>
              <Text>{lpo.status}</Text>
            </View>
          </View>
        </View>

        <View style={styles.metaInfo}>
          <BuyerBlock client={client} />
          <View style={styles.quoteDetails}>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>LPO No:</Text>
              <Text style={styles.detailValue}>{lpo.lpo_number}</Text>
            </View>
            {lpo.customer_po_number ? (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Customer PO:</Text>
                <Text style={styles.detailValue}>{lpo.customer_po_number}</Text>
              </View>
            ) : null}
            {quotationNumber ? (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Quote No:</Text>
                <Text style={styles.detailValue}>{quotationNumber}</Text>
              </View>
            ) : null}
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>LPO Date:</Text>
              <Text style={styles.detailValue}>{lpo.lpo_date}</Text>
            </View>
            {lpo.expected_delivery_date ? (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Expected Delivery:</Text>
                <Text style={styles.detailValue}>{lpo.expected_delivery_date}</Text>
              </View>
            ) : null}
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Currency:</Text>
              <Text style={styles.detailValue}>AED</Text>
            </View>
          </View>
        </View>

        <View style={styles.table}>
          <View style={styles.tableHeader}>
            <Text style={styles.colDesc}>Description</Text>
            <Text style={styles.colQty}>Ordered</Text>
            <Text style={styles.colInv}>Invoiced</Text>
            <Text style={styles.colRem}>Remain</Text>
            <Text style={styles.colUnit}>Unit</Text>
            <Text style={styles.colNet}>Net</Text>
            <Text style={styles.colRate}>VAT%</Text>
            <Text style={styles.colVat}>VAT</Text>
            <Text style={styles.colGross}>Gross</Text>
          </View>
          {(lpo.items ?? []).map((item, index) => (
            <LineRow key={item.id || index} item={item} />
          ))}
        </View>

        <View style={styles.summary}>
          <View style={styles.summaryRow}>
            <Text style={styles.detailLabel}>Subtotal (excl. VAT):</Text>
            <Text>AED {money(lpo.subtotal)}</Text>
          </View>
          <View style={styles.summaryRow}>
            <Text style={styles.detailLabel}>VAT:</Text>
            <Text>AED {money(lpo.tax_amount)}</Text>
          </View>
          <View style={styles.summaryTotal}>
            <Text>Total (AED):</Text>
            <Text>{money(lpo.total_amount)}</Text>
          </View>
        </View>

        {lpo.notes ? (
          <View style={styles.notes}>
            <Text style={styles.detailLabel}>Notes</Text>
            <Text>{lpo.notes}</Text>
          </View>
        ) : null}

        <View style={styles.footer}>
          <Text>LPO — amounts in AED. This is not a tax invoice.</Text>
          <Text>Generated by InvoiceSaaS</Text>
        </View>
      </Page>
    </Document>
  );
};

export async function downloadLpoPdf(args: {
  lpo: CustomerPurchaseOrder;
  client?: Client;
  workspace?: Workspace;
  quotationNumber?: string;
}): Promise<void> {
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
