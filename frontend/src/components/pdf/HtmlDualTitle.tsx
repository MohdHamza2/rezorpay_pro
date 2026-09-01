import type { ReactNode } from 'react';
import css from './pdfBilingual.module.css';

type EnTag = 'span' | 'h2' | 'h3';

export function HtmlDualTitle({
  en,
  ar,
  enTestId,
  arTestId,
  enAs = 'span',
}: {
  en: string;
  ar: string;
  enTestId: string;
  arTestId: string;
  enAs?: EnTag;
}) {
  const En = enAs;
  return (
    <div className={css.dualTitle}>
      <En className={css.enTitle} data-testid={enTestId}>
        {en}
      </En>
      <span className={css.arTitle} data-testid={arTestId} lang="ar" dir="rtl">
        {ar}
      </span>
    </div>
  );
}

export function HtmlStackedLine({
  en,
  ar,
  testId,
}: {
  en: string;
  ar: string;
  testId?: string;
}) {
  return (
    <p className={css.chromeBlock} data-testid={testId}>
      <span>{en}</span>
      <span className={css.arLabel} lang="ar" dir="rtl">
        {ar}
      </span>
    </p>
  );
}

export function HtmlStackHead({ en, ar }: { en: string; ar: string }): ReactNode {
  return (
    <span className={css.stackHead}>
      <span>{en}</span>
      <span className={css.arLabel} lang="ar" dir="rtl">
        {ar}
      </span>
    </span>
  );
}
