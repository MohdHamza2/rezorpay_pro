import { Document, Page, Text, View, StyleSheet, pdf } from '@react-pdf/renderer';
import type { Client } from '../../api/clients';
import type { CreditNote, CreditNoteItem } from '../../api/creditNotes';
import type { Invoice } from '../../api/invoices';
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
  noteDetails: { width: '44%' },
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
    color: '#93c5fd',
    opacity: 0.35,
    letterSpacing: 6,
  },
});

function money(value: string | number | null | undefined): string {
  return Number(value ?? 0).toFixed(2);
}

function snapFirst(
  snapshot: string | null | undefined,
  live: string | null | undefined,
): string {
  const frozen = (snapshot ?? '').trim();
  if (frozen) return frozen;
  return (live ?? '').trim();
}

function discountLabel(item: CreditNoteItem): string {
  const pct = Number(item.discount_percent ?? 0);
  const amt = Number(item.discount_amount ?? 0);
  if (pct > 0) return `${money(pct)}%`;
  if (amt > 0) return money(amt);
  return '—';
}

function SellerBlock({
  cn,
  workspace,
}: {
  cn: CreditNote;
  workspace?: Workspace;
}) {
  const name = snapFirst(cn.seller_name_snapshot, workspace?.name);
  const address = snapFirst(cn.seller_address_snapshot, workspace?.address);
  const trn = snapFirst(cn.seller_trn_snapshot, workspace?.trn);
  return (
    <View style={styles.headerLeft}>
      <Text style={styles.companyName}>{name || 'Your Company LLC'}</Text>
      {address ? <Text style={styles.companyDetails}>{address}</Text> : null}
      {trn ? <Text style={styles.companyDetails}>TRN: {trn}</Text> : null}
    </View>
  );
}

function BuyerBlock({ cn, client }: { cn: CreditNote; client?: Client }) {
  const name = snapFirst(cn.buyer_name_snapshot, client?.name);
  const address = snapFirst(cn.buyer_address_snapshot, client?.address);
  const trn = snapFirst(cn.buyer_trn_snapshot, client?.tax_id);
  return (
    <View style={styles.clientSection}>
      <Text style={styles.clientTitle}>CREDIT TO:</Text>
      <Text style={styles.clientName}>{name || 'Valued Customer'}</Text>
      {address ? <Text style={styles.companyDetails}>{address}</Text> : null}
      {trn ? <Text style={styles.companyDetails}>TRN: {trn}</Text> : null}
    </View>
  );
}

function LineRow({ item }: { item: CreditNoteItem }) {
  return (
    <View style={styles.tableRow}>
      <View style={styles.colDesc}>
        <Text>{item.description}</Text>
        {item.sku_snapshot ? <Text style={styles.sku}>SKU: {item.sku_snapshot}</Text> : null}
      </View>
      <Text style={styles.colQty}>{money(item.quantity)}</Text>
      <Text style={styles.colUnit}>{money(item.unit_price)}</Text>
      <Text style={styles.colDisc}>{discountLabel(item)}</Text>
      <Text style={styles.colNet}>{money(item.line_net)}</Text>
      <Text style={styles.colRate}>{money(item.tax_rate)}%</Text>
      <Text style={styles.colVat}>{money(item.tax_amount)}</Text>
      <Text style={styles.colGross}>{money(item.total_price)}</Text>
    </View>
  );
}

export const CreditNotePDF = ({
  cn,
  client,
  workspace,
  invoice,
}: {
  cn: CreditNote;
  client?: Client;
  workspace?: Workspace;
  invoice?: Invoice;
}) => {
  const originalNumber = cn.original_invoice_number || invoice?.invoice_number || '—';
  const originalDate = cn.original_issue_date || invoice?.issue_date || '—';
  return (
    <Document>
      <Page size="A4" style={styles.page}>
        {cn.status === 'DRAFT' ? <Text style={styles.watermark}>DRAFT</Text> : null}
        <View style={styles.header}>
          <SellerBlock cn={cn} workspace={workspace} />
          <View style={styles.headerRight}>
            <Text style={styles.title}>Tax Credit Note</Text>
            <View style={styles.statusBadge}>
              <Text>{cn.status}</Text>
            </View>
          </View>
        </View>

        <View style={styles.metaInfo}>
          <BuyerBlock cn={cn} client={client} />
          <View style={styles.noteDetails}>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Credit Note No:</Text>
              <Text style={styles.detailValue}>{cn.credit_note_number}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Issue Date:</Text>
              <Text style={styles.detailValue}>{cn.issue_date}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Original Invoice:</Text>
              <Text style={styles.detailValue}>{originalNumber}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Original Issue Date:</Text>
              <Text style={styles.detailValue}>{originalDate}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Currency:</Text>
              <Text style={styles.detailValue}>AED</Text>
            </View>
          </View>
        </View>

        <View style={styles.table}>
          <View style={styles.tableHeader}>
            <Text style={styles.colDesc}>Description</Text>
            <Text style={styles.colQty}>Qty</Text>
            <Text style={styles.colUnit}>Unit</Text>
            <Text style={styles.colDisc}>Disc</Text>
            <Text style={styles.colNet}>Net</Text>
            <Text style={styles.colRate}>VAT%</Text>
            <Text style={styles.colVat}>VAT AED</Text>
            <Text style={styles.colGross}>Gross</Text>
          </View>
          {(cn.items ?? []).map((item, index) => (
            <LineRow key={item.id || index} item={item} />
          ))}
        </View>

        <View style={styles.summary}>
          <View style={styles.summaryRow}>
            <Text style={styles.detailLabel}>Subtotal (excl. VAT):</Text>
            <Text>AED {money(cn.subtotal)}</Text>
          </View>
          <View style={styles.summaryRow}>
            <Text style={styles.detailLabel}>VAT:</Text>
            <Text>AED {money(cn.tax_amount)}</Text>
          </View>
          <View style={styles.summaryTotal}>
            <Text>Credit total (AED):</Text>
            <Text>{money(cn.total_amount)}</Text>
          </View>
        </View>

        <View style={styles.footer}>
          <Text>Tax Credit Note — amounts in AED. English only.</Text>
          <Text>Generated by InvoiceSaaS</Text>
        </View>
      </Page>
    </Document>
  );
};

export async function downloadCreditNotePdf(args: {
  cn: CreditNote;
  client?: Client;
  workspace?: Workspace;
  invoice?: Invoice;
}): Promise<void> {
  const blob = await pdf(
    <CreditNotePDF
      cn={args.cn}
      client={args.client}
      workspace={args.workspace}
      invoice={args.invoice}
    />,
  ).toBlob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `TaxCreditNote_${args.cn.credit_note_number}.pdf`;
  anchor.click();
  URL.revokeObjectURL(url);
}
