import { Text, View, StyleSheet } from '@react-pdf/renderer';
import { PDF_FONT_AR } from './pdfFonts';

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-end',
    width: '100%',
    marginBottom: 16,
  },
  en: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#111827',
    fontFamily: 'Helvetica',
  },
  ar: {
    fontFamily: PDF_FONT_AR,
    fontWeight: 'normal',
    fontSize: 16,
    color: '#111827',
    textAlign: 'right',
  },
});

export function PdfDualTitle({ en, ar }: { en: string; ar: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.en}>{en}</Text>
      <Text style={styles.ar}>{ar}</Text>
    </View>
  );
}
