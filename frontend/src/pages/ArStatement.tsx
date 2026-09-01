import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { getArStatement } from '../api/clients';
import type { ArStatement as StatementDoc, ArStatementLine, StatementDocType } from '../api/clients';
import { isHttpNotFound } from '../api/errors';
import { HtmlDualTitle, HtmlStackHead } from '../components/pdf/HtmlDualTitle';
import { agingBucketAr, statementTypeAr } from '../components/pdf/pdfChrome';
import bilingual from '../components/pdf/pdfBilingual.module.css';
import { PDF_LABELS } from '../components/pdf/pdfLabels';
import { PDF_TITLES } from '../components/pdf/pdfTitles';
import { downloadStatementPdf } from '../components/pdf/StatementPDF';
import { StatementPdfPreview } from '../components/pdf/StatementPdfPreview';
import { Skeleton } from '../components/Skeleton';
import { formatAed } from './quotationHelpers';
import {
  AGING_ROWS,
  OUTSTANDING_COPY,
  PDC_SUCCESS_NOTE,
  defaultStatementRange,
  formatMoney,
  isCreditNoteLine,
  isPaymentLine,
  isPendingLine,
  retryUnlessClientError,
  statementRangeSchema,
  type StatementRange,
} from './statementHelpers';
import quote from './Quotations.module.css';
import styles from './ArStatement.module.css';

function rowTone(docType: StatementDocType): string {
  if (docType === 'PAYMENT') return styles.linePaid;
  if (docType === 'TAX_CREDIT_NOTE') return styles.lineCredit;
  if (docType === 'PAYMENT_PENDING') return styles.linePending;
  if (docType === 'OPENING') return styles.lineOpening;
  return '';
}

function typeTone(docType: StatementDocType): string {
  if (isPaymentLine(docType)) return styles.typePaid;
  if (isCreditNoteLine(docType)) return styles.typeCredit;
  if (isPendingLine(docType)) return styles.typePending;
  return '';
}

function creditTone(docType: StatementDocType): string {
  if (isPaymentLine(docType)) return styles.creditPaid;
  if (isCreditNoteLine(docType)) return styles.creditNote;
  return '';
}

function typeExtra(line: ArStatementLine): string | null {
  if (line.payment_method) return line.payment_method;
  if (isPendingLine(line.doc_type)) return 'not cleared';
  return null;
}

function creditDisplay(line: ArStatementLine): string {
  if (isPendingLine(line.doc_type)) return formatMoney(0);
  return formatMoney(line.credit);
}

function LinesTable({ lines }: { lines: ArStatementLine[] }) {
  return (
    <div className={quote.tableContainer}>
      <table className={quote.table} data-testid="statement-lines">
        <thead>
          <tr>
            <th>
              <HtmlStackHead en={PDF_LABELS.date.en} ar={PDF_LABELS.date.ar} />
            </th>
            <th>
              <HtmlStackHead en={PDF_LABELS.type.en} ar={PDF_LABELS.type.ar} />
            </th>
            <th>
              <HtmlStackHead en={PDF_LABELS.number.en} ar={PDF_LABELS.number.ar} />
            </th>
            <th className={styles.num}>
              <HtmlStackHead en={PDF_LABELS.debit.en} ar={PDF_LABELS.debit.ar} />
            </th>
            <th className={styles.num}>
              <HtmlStackHead en={PDF_LABELS.credit.en} ar={PDF_LABELS.credit.ar} />
            </th>
            <th className={styles.num}>
              <HtmlStackHead en={PDF_LABELS.balance.en} ar={PDF_LABELS.balance.ar} />
            </th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line, index) => (
            <tr
              key={`${line.doc_type}-${line.number ?? index}-${line.date}`}
              className={rowTone(line.doc_type)}
              data-testid={`statement-line-${line.doc_type}`}
              data-doc-type={line.doc_type}
            >
              <td>{line.date}</td>
              <td className={typeTone(line.doc_type)}>
                <span className={bilingual.stackHead}>
                  <span>{line.doc_type_label}</span>
                  <span className={bilingual.arLabel} lang="ar" dir="rtl">
                    {statementTypeAr(line.doc_type)}
                  </span>
                </span>
                {typeExtra(line) ? <span className={styles.sub}>{typeExtra(line)}</span> : null}
              </td>
              <td>
                {line.number || '—'}
                {line.reference ? <span className={styles.sub}>{line.reference}</span> : null}
              </td>
              <td className={styles.num}>{formatMoney(line.debit)}</td>
              <td className={`${styles.num} ${creditTone(line.doc_type)}`}>{creditDisplay(line)}</td>
              <td className={styles.num}>{formatMoney(line.running_balance)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TotalsFooter({ data }: { data: StatementDoc }) {
  return (
    <div className={quote.totals}>
      <div className={quote.totalRow}>
        <HtmlStackHead en="Billed" ar={PDF_LABELS.billed.ar} />
        <span data-testid="statement-billed">{formatAed(data.totals.billed)}</span>
      </div>
      <div className={quote.totalRow}>
        <HtmlStackHead en="Paid (SUCCESS payments)" ar={PDF_LABELS.paidSuccess.ar} />
        <span data-testid="statement-paid">{formatAed(data.totals.paid)}</span>
      </div>
      <div className={quote.totalRow}>
        <HtmlStackHead
          en="Credited (tax credit notes)"
          ar={PDF_LABELS.creditedTaxCreditNotes.ar}
        />
        <span data-testid="statement-credited">{formatAed(data.totals.credited)}</span>
      </div>
      <div className={quote.totalStrong}>
        <HtmlStackHead en="Amount due now" ar={PDF_LABELS.amountDueNow.ar} />
        <span data-testid="statement-amount-due">{formatAed(data.amount_due_now)}</span>
      </div>
      <div className={quote.totalRow}>
        <HtmlStackHead en="Unapplied credit" ar={PDF_LABELS.unappliedCredit.ar} />
        <span className={styles.unapplied} data-testid="statement-unapplied">
          {formatAed(data.credit_balance)}
        </span>
      </div>
    </div>
  );
}

function AgingTable({ data }: { data: StatementDoc }) {
  return (
    <div>
      <h3>
        <HtmlStackHead en={PDF_LABELS.aging.en} ar={PDF_LABELS.aging.ar} />
      </h3>
      <table className={styles.agingTable} data-testid="statement-aging">
        <thead>
          <tr>
            <th>Bucket</th>
            <th className={styles.num}>Amount</th>
          </tr>
        </thead>
        <tbody>
          {AGING_ROWS.map((row) => (
            <tr key={row.key} data-testid={`statement-aging-${row.key}`}>
              <td>
                <HtmlStackHead en={row.label} ar={agingBucketAr(row.key)} />
              </td>
              <td className={styles.num}>{formatAed(data.aging.buckets[row.key])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const ArStatement = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const defaults = defaultStatementRange();
  const [applied, setApplied] = useState<StatementRange>(defaults);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<StatementRange>({
    resolver: zodResolver(statementRangeSchema),
    defaultValues: defaults,
  });

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['ar-statement', id, applied.from, applied.to, applied.as_of],
    queryFn: () => getArStatement(id!, applied),
    enabled: Boolean(id),
    retry: retryUnlessClientError,
  });

  const onApply = (values: StatementRange) => {
    setApplied({ from: values.from, to: values.to, as_of: values.as_of });
  };

  const handleDownload = async () => {
    if (!id) return;
    setPdfBusy(true);
    try {
      const fresh = await getArStatement(id, applied);
      await downloadStatementPdf(fresh);
    } catch (err) {
      const axiosError = err as { response?: unknown };
      if (!axiosError.response) toast.error('Could not generate Account Statement PDF');
    } finally {
      setPdfBusy(false);
    }
  };

  if (isError && isHttpNotFound(error)) {
    return (
      <div className={quote.container}>
        <p data-testid="statement-not-found">Client not found.</p>
      </div>
    );
  }

  return (
    <div className={quote.container} data-testid="ar-statement">
      <div className={quote.header}>
        <HtmlDualTitle
          en={PDF_TITLES.accountStatement.en}
          ar={PDF_TITLES.accountStatement.ar}
          enTestId="statement-pdf-title"
          arTestId="statement-pdf-title-ar"
          enAs="h2"
        />
        <div className={styles.headerActions}>
          <button type="button" className={quote.secondaryBtn} onClick={() => navigate('/clients')}>
            Back to clients
          </button>
          <button
            type="button"
            className={quote.secondaryBtn}
            data-testid="statement-preview-pdf"
            disabled={!data}
            onClick={() => setPreviewOpen(true)}
          >
            Preview PDF
          </button>
          <button
            type="button"
            className={quote.secondaryBtn}
            data-testid="statement-download-pdf"
            disabled={!data || pdfBusy}
            onClick={() => void handleDownload()}
          >
            Download PDF
          </button>
        </div>
      </div>

      <form
        className={styles.filters}
        onSubmit={handleSubmit(onApply, (formErrors) => {
          const msg = formErrors.from?.message || formErrors.to?.message || formErrors.as_of?.message;
          if (msg) toast.error(msg);
        })}
      >
        <div className={quote.filterGroup}>
          <label htmlFor="statement-from">From</label>
          <input id="statement-from" type="date" data-testid="statement-from" {...register('from')} />
          {errors.from && <span className={styles.errorText}>{errors.from.message}</span>}
        </div>
        <div className={quote.filterGroup}>
          <label htmlFor="statement-to">To</label>
          <input id="statement-to" type="date" data-testid="statement-to" {...register('to')} />
          {errors.to && <span className={styles.errorText}>{errors.to.message}</span>}
        </div>
        <div className={quote.filterGroup}>
          <label htmlFor="statement-as-of">As of</label>
          <input
            id="statement-as-of"
            type="date"
            data-testid="statement-as-of"
            {...register('as_of')}
          />
          {errors.as_of && <span className={styles.errorText}>{errors.as_of.message}</span>}
        </div>
        <button type="submit" className={quote.primaryBtn} data-testid="statement-apply">
          Apply
        </button>
      </form>

      <p className={styles.copy} data-testid="statement-copy">
        {OUTSTANDING_COPY}
      </p>
      <p className={styles.copy} data-testid="statement-pdc-note">
        {PDC_SUCCESS_NOTE}
      </p>

      {isLoading ? (
        <Skeleton height="320px" />
      ) : data ? (
        <div className={quote.pageCard}>
          <p>
            {data.client.name} · {data.from}–{data.to} · as of {data.as_of} · {data.currency || 'AED'}
          </p>
          <LinesTable lines={data.lines} />
          <TotalsFooter data={data} />
          <AgingTable data={data} />
        </div>
      ) : (
        <p className={quote.hint}>Could not load statement. Adjust the date range and try again.</p>
      )}

      {previewOpen && data ? (
        <StatementPdfPreview data={data} onClose={() => setPreviewOpen(false)} />
      ) : null}
    </div>
  );
};
