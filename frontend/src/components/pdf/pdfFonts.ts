import { Font } from '@react-pdf/renderer';
import notoUrl from '../../assets/fonts/NotoNaskhArabic-Regular.ttf?url';

const FAMILY = 'NotoNaskhArabic';

let registered = false;

export function registerPdfFonts(): void {
  if (registered) {
    return;
  }
  Font.register({ family: FAMILY, src: notoUrl });
  Font.registerHyphenationCallback((word) => [word]);
  registered = true;
}

export const PDF_FONT_AR = FAMILY;
export const PDF_FONT_EN = 'Helvetica';
