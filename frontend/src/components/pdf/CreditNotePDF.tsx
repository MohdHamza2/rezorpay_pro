import { Document, Page, Text, View, StyleSheet, pdf } from '@react-pdf/renderer';
import type { Client } from '../../api/clients';
import type { CreditNote, CreditNoteItem } from '../../api/creditNotes';
import type { Invoice } from '../../api/invoices';
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
  noteDetails: { width: '44%' },
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

function snapFirst(snapshot: string | null | undefined, live: string | null | undefined): string {
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

function SellerBlock({ cn, workspace }: { cn: CreditNote; workspace?: Workspace }) {
  const name = snapFirst(cn.seller_name_snapshot, workspace?.name);
  const address = snapFirst(cn.seller_address_snapshot, workspace?.address);
  const trn = snapFirst(cn.seller_trn_snapshot, workspace?.trn);
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

function BuyerBlock({ cn, client }: { cn: CreditNote; client?: Client }) {
  const name = snapFirst(cn.buyer_name_snapshot, client?.name);
  const address = snapFirst(cn.buyer_address_snapshot, client?.address);
  const trn = snapFirst(cn.buyer_trn_snapshot, client?.tax_id);
  return (
    <View style={styles.clientSection}>
      <PdfStackedLabel en={PDF_LABELS.creditTo.en} ar={PDF_LABELS.creditTo.ar} boldEn />
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
        {cn.status === 'DRAFT' ? (
          <PdfWatermark
            en={PDF_LABELS.watermarkDraft.en}
            ar={PDF_LABELS.watermarkDraft.ar}
            color="#93c5fd"
          />
        ) : null}
        <View style={styles.header}>
          <SellerBlock cn={cn} workspace={workspace} />
          <View style={styles.headerRight}>
            <View style={styles.statusBadge}>
              <Text>{cn.status}</Text>
            </View>
          </View>
        </View>
        <PdfDualTitle en={PDF_TITLES.taxCreditNote.en} ar={PDF_TITLES.taxCreditNote.ar} />

        <View style={styles.metaInfo}>
          <BuyerBlock cn={cn} client={client} />
          <View style={styles.noteDetails}>
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.creditNoteNo.en} ar={PDF_LABELS.creditNoteNo.ar} />
              <Text style={styles.detailValue}>{cn.credit_note_number}</Text>
            </View>
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.issueDate.en} ar={PDF_LABELS.issueDate.ar} />
              <Text style={styles.detailValue}>{cn.issue_date}</Text>
            </View>
            <View style={styles.detailRow}>
              <PdfStackedLabel en={PDF_LABELS.originalInvoice.en} ar={PDF_LABELS.originalInvoice.ar} />
              <Text style={styles.detailValue}>{originalNumber}</Text>
            </View>
            <View style={styles.detailRow}>
              <PdfStackedLabel
                en={PDF_LABELS.originalIssueDate.en}
                ar={PDF_LABELS.originalIssueDate.ar}
              />
              <Text style={styles.detailValue}>{originalDate}</Text>
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
          {(cn.items ?? []).map((item, index) => (
            <LineRow key={item.id || index} item={item} />
          ))}
        </View>

        <View style={styles.summary}>
          <View style={styles.summaryRow}>
            <PdfStackedLabel en={PDF_LABELS.subtotalExclVat.en} ar={PDF_LABELS.subtotalExclVat.ar} />
            <Text>AED {money(cn.subtotal)}</Text>
          </View>
          <View style={styles.summaryRow}>
            <PdfStackedLabel en={PDF_LABELS.vat.en} ar={PDF_LABELS.vat.ar} />
            <Text>AED {money(cn.tax_amount)}</Text>
          </View>
          <View style={styles.summaryTotal}>
            <PdfStackedLabel en={PDF_LABELS.creditTotalAed.en} ar={PDF_LABELS.creditTotalAed.ar} boldEn />
            <Text>{money(cn.total_amount)}</Text>
          </View>
        </View>

        <PdfBilingualFooter />
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
  registerPdfFonts();
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
