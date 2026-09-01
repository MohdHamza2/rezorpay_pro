import { Text, View, StyleSheet } from '@react-pdf/renderer';
import type { Style } from '@react-pdf/types';
import type { StatementDocType } from '../../api/clients';
import { PDF_FONT_AR } from './pdfFonts';
import { PDF_LABELS } from './pdfLabels';

const chrome = StyleSheet.create({
  ar: {
    fontFamily: PDF_FONT_AR,
    fontWeight: 'normal',
    fontSize: 6,
    color: '#6b7280',
  },
  arHead: {
    fontFamily: PDF_FONT_AR,
    fontWeight: 'normal',
    fontSize: 6,
    color: '#374151',
  },
  arFoot: {
    fontFamily: PDF_FONT_AR,
    fontWeight: 'normal',
    fontSize: 7,
    color: '#6b7280',
    marginTop: 2,
  },
  labelCol: { flexDirection: 'column' },
  footerPinned: {
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
  footerFlow: {
    marginTop: 18,
    borderTop: '1px solid #e5e7eb',
    paddingTop: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    color: '#6b7280',
    fontSize: 8,
  },
  footerLeft: { flexDirection: 'column', maxWidth: '70%' },
  wmWrap: {
    position: 'absolute',
    top: '40%',
    left: 0,
    right: 0,
    alignItems: 'center',
    opacity: 0.35,
  },
  wmEn: {
    fontSize: 48,
    letterSpacing: 6,
    textAlign: 'center',
  },
  wmAr: {
    fontFamily: PDF_FONT_AR,
    fontWeight: 'normal',
    fontSize: 22,
    textAlign: 'center',
    marginTop: 4,
  },
});

type Pair = { en: string; ar: string };

export function PdfStackedLabel({ en, ar, boldEn }: Pair & { boldEn?: boolean }) {
  return (
    <View style={chrome.labelCol}>
      <Text style={boldEn ? { fontWeight: 'bold' } : undefined}>{en}</Text>
      <Text style={chrome.ar}>{ar}</Text>
    </View>
  );
}

export function PdfHeadCell({ en, ar, style }: Pair & { style: Style }) {
  return (
    <View style={style}>
      <Text>{en}</Text>
      <Text style={chrome.arHead}>{ar}</Text>
    </View>
  );
}

export function PdfWatermark({ en, ar, color }: Pair & { color: string }) {
  return (
    <View style={chrome.wmWrap} fixed>
      <Text style={[chrome.wmEn, { color }]}>{en}</Text>
      <Text style={[chrome.wmAr, { color }]}>{ar}</Text>
    </View>
  );
}

export function PdfBilingualFooter({ flow }: { flow?: boolean }) {
  return (
    <View style={flow ? chrome.footerFlow : chrome.footerPinned}>
      <View style={chrome.footerLeft}>
        <Text>{PDF_LABELS.footerDisclaimer.en}</Text>
        <Text style={chrome.arFoot}>{PDF_LABELS.footerDisclaimer.ar}</Text>
      </View>
      <Text>{PDF_LABELS.generatedBy.en}</Text>
    </View>
  );
}

export function PdfTrnLine({ digits }: { digits: string }) {
  return (
    <View>
      <Text>TRN: {digits}</Text>
      <Text style={chrome.ar}>{PDF_LABELS.trn.ar}</Text>
    </View>
  );
}

export function PdfArText({ children }: { children: string }) {
  return <Text style={chrome.ar}>{children}</Text>;
}

export function statementTypeAr(docType: StatementDocType): string {
  if (docType === 'OPENING') return PDF_LABELS.openingBalance.ar;
  if (docType === 'TAX_INVOICE') return PDF_LABELS.taxInvoice.ar;
  if (docType === 'PAYMENT') return PDF_LABELS.payment.ar;
  if (docType === 'PAYMENT_PENDING') return PDF_LABELS.paymentPending.ar;
  return PDF_LABELS.taxCreditNote.ar;
}

export function agingBucketAr(key: string): string {
  if (key === 'current') return PDF_LABELS.current.ar;
  if (key === 'days_1_30') return PDF_LABELS.aging1to30.ar;
  if (key === 'days_31_60') return PDF_LABELS.aging31to60.ar;
  if (key === 'days_61_90') return PDF_LABELS.aging61to90.ar;
  return PDF_LABELS.aging90plus.ar;
}
