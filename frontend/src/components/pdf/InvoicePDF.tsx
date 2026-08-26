import { Document, Page, Text, View, StyleSheet } from '@react-pdf/renderer';
import type { Invoice } from '../../api/invoices';

const styles = StyleSheet.create({
  page: { padding: 30, fontSize: 10, fontFamily: 'Helvetica' },
  header: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 30 },
  headerLeft: { flexDirection: 'column' },
  headerRight: { flexDirection: 'column', alignItems: 'flex-end' },
  title: { fontSize: 24, fontWeight: 'bold', color: '#111827' },
  companyName: { fontSize: 16, fontWeight: 'bold', marginTop: 10 },
  companyDetails: { color: '#4b5563', marginTop: 4, lineHeight: 1.4 },

  metaInfo: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 30 },
  clientSection: { flexDirection: 'column', width: '50%' },
  clientTitle: { fontSize: 10, fontWeight: 'bold', color: '#6b7280', marginBottom: 4 },
  clientName: { fontSize: 14, fontWeight: 'bold', color: '#111827' },

  invoiceDetails: { width: '40%' },
  detailRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4, borderBottom: '1px solid #f3f4f6' },
  detailLabel: { color: '#6b7280' },
  detailValue: { fontWeight: 'bold' },

  table: { width: '100%', marginTop: 20 },
  tableHeader: { flexDirection: 'row', backgroundColor: '#f9fafb', padding: 8, borderBottom: '1px solid #e5e7eb', fontWeight: 'bold' },
  tableRow: { flexDirection: 'row', padding: 8, borderBottom: '1px solid #e5e7eb' },
  col1: { width: '40%' },
  col2: { width: '20%', textAlign: 'right' },
  col3: { width: '20%', textAlign: 'right' },
  col4: { width: '20%', textAlign: 'right' },

  summary: { width: '40%', alignSelf: 'flex-end', marginTop: 20 },
  summaryRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  summaryTotal: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderTop: '2px solid #e5e7eb', marginTop: 4, fontWeight: 'bold', fontSize: 12 },

  footer: { position: 'absolute', bottom: 30, left: 30, right: 30, borderTop: '1px solid #e5e7eb', paddingTop: 10, flexDirection: 'row', justifyContent: 'space-between', color: '#6b7280', fontSize: 8 },
  statusBadge: { padding: '4 8', borderRadius: 4, color: 'white', backgroundColor: '#2563eb', alignSelf: 'flex-start', marginTop: 10, fontSize: 10 }
});

export const InvoicePDF = ({ invoice, client, workspace }: { invoice: Invoice, client?: any, workspace?: any }) => (
  <Document>
    <Page size="A4" style={styles.page}>
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Text style={styles.companyName}>{workspace?.name || 'Your Company LLC'}</Text>
          <Text style={styles.companyDetails}>{workspace?.trn ? "TRN: " + workspace.trn : ''}</Text>
          <Text style={styles.companyDetails}>{workspace?.whatsapp_number ? "WA: " + workspace.whatsapp_number : ''}</Text>
        </View>
        <View style={styles.headerRight}>
          <Text style={styles.title}>INVOICE</Text>
          <View style={styles.statusBadge}>
            <Text>{invoice.status}</Text>
          </View>
        </View>
      </View>

      <View style={styles.metaInfo}>
        <View style={styles.clientSection}>
          <Text style={styles.clientTitle}>BILL TO:</Text>
          <Text style={styles.clientName}>{client?.name || 'Valued Customer'}</Text>
          {client?.email && <Text style={{ color: '#4b5563', marginTop: 4 }}>{client.email}</Text>}
        </View>

        <View style={styles.invoiceDetails}>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Invoice No:</Text>
            <Text style={styles.detailValue}>{invoice.invoice_number}</Text>
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Issue Date:</Text>
            <Text style={styles.detailValue}>{invoice.issue_date}</Text>
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Due Date:</Text>
            <Text style={styles.detailValue}>{invoice.due_date}</Text>
          </View>
        </View>
      </View>

      <View style={styles.table}>
        <View style={styles.tableHeader}>
          <Text style={styles.col1}>Item Description</Text>
          <Text style={styles.col2}>Qty</Text>
          <Text style={styles.col3}>Unit Price</Text>
          <Text style={styles.col4}>Total</Text>
        </View>

        {invoice.items.map((item, index) => (
          <View key={index} style={styles.tableRow}>
            <Text style={styles.col1}>{item.description}</Text>
            <Text style={styles.col2}>{item.quantity}</Text>
            <Text style={styles.col3}>{(item.unit_price ?? 0).toFixed(2)}</Text>
            <Text style={styles.col4}>{(item.total_price ?? 0).toFixed(2)}</Text>
          </View>
        ))}
      </View>

      <View style={styles.summary}>
        <View style={styles.summaryRow}>
          <Text style={styles.detailLabel}>Subtotal:</Text>
          <Text>{(invoice.subtotal ?? 0).toFixed(2)}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={styles.detailLabel}>Tax Amount:</Text>
          <Text>{(invoice.tax_amount ?? 0).toFixed(2)}</Text>
        </View>
        <View style={styles.summaryTotal}>
          <Text>Total (AED):</Text>
          <Text>{(invoice.total_amount ?? 0).toFixed(2)}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={styles.detailLabel}>Amount Paid:</Text>
          <Text>{(invoice.amount_paid || 0).toFixed(2)}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={{ fontWeight: 'bold' }}>Balance Due:</Text>
          <Text style={{ fontWeight: 'bold' }}>{(invoice.balance_due || 0).toFixed(2)}</Text>
        </View>
      </View>

      <View style={styles.footer}>
        <Text>Thank you for your business.</Text>
        <Text>Generated by InvoiceSaaS</Text>
      </View>
    </Page>
  </Document>
);
