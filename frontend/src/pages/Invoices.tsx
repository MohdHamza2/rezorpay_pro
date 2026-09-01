import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getInvoices,
  getInvoice,
  createInvoice,
  updateInvoice,
  sendInvoice,
  voidInvoice,
  recordPayment,
} from '../api/invoices';
import type {
  Invoice,
  InvoiceCreatePayload,
  InvoiceItem,
  InvoiceItemWrite,
  InvoiceListItem,
  InvoiceStatus,
  InvoiceUpdatePayload,
  PaymentData,
} from '../api/invoices';
import { extractApiError } from '../api/errors';
import { getClients } from '../api/clients';
import { getProductPrices, getProducts, PRODUCT_PAGE_SIZE } from '../api/products';
import { useForm, useFieldArray } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Edit2, Plus, Trash2, Send, XCircle, DollarSign, Download, Eye, FileMinus } from 'lucide-react';
import { pdf } from '@react-pdf/renderer';
import { InvoicePDF } from '../components/pdf/InvoicePDF';
import { InvoicePdfPreview } from '../components/pdf/InvoicePdfPreview';
import { getCurrentWorkspace } from '../api/workspaces';
import toast from 'react-hot-toast';
import { Skeleton } from '../components/Skeleton';
import { isCreditableStatus } from './creditNoteHelpers';
import { InvoiceArPanel } from './InvoiceArPanel';
import { paymentRecordedMessage } from './paymentHelpers';
import styles from './Invoices.module.css';

type LineForm = {
  product_id?: string;
  description?: string;
  quantity: string;
  unit_price?: string;
  tax_rate?: string;
  discount_percent?: string;
  discount_amount?: string;
};

const invoiceItemSchema = z
  .object({
    product_id: z.string().optional(),
    description: z.string().optional(),
    quantity: z.string().min(1, 'Qty required'),
    unit_price: z.string().optional(),
    tax_rate: z.string().optional(),
    discount_percent: z.string().optional(),
    discount_amount: z.string().optional(),
  })
  .superRefine(refineInvoiceItem);

const invoiceSchema = z
  .object({
    client_id: z.string().min(1, 'Client required'),
    issue_date: z.string().min(1, 'Issue date required'),
    supply_date: z.string().min(1, 'Supply date required'),
    due_date: z.string().min(1, 'Due date required'),
    items: z.array(invoiceItemSchema).min(1, 'At least one item required'),
  })
  .superRefine(refineInvoiceDates);

type InvoiceFormValues = z.infer<typeof invoiceSchema>;

function parseAmount(value: string | undefined): number | undefined {
  if (value == null || value.trim() === '') return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function refineInvoiceItem(item: LineForm, ctx: z.RefinementCtx) {
  const hasProduct = Boolean(item.product_id?.trim());
  if (!hasProduct && !item.description?.trim()) {
    ctx.addIssue({ code: 'custom', message: 'Description required', path: ['description'] });
  }
  if (!hasProduct && parseAmount(item.unit_price) === undefined) {
    ctx.addIssue({ code: 'custom', message: 'Price required', path: ['unit_price'] });
  }
  const qty = parseAmount(item.quantity);
  if (qty === undefined || qty <= 0) {
    ctx.addIssue({ code: 'custom', message: 'Qty must be greater than 0', path: ['quantity'] });
  }
  addRateAndDiscountIssues(item, ctx);
}

function addRateAndDiscountIssues(item: LineForm, ctx: z.RefinementCtx) {
  const tax = parseAmount(item.tax_rate);
  if (item.tax_rate?.trim() && (tax === undefined || tax < 0 || tax > 100)) {
    ctx.addIssue({ code: 'custom', message: 'Tax rate must be 0–100', path: ['tax_rate'] });
  }
  const percent = parseAmount(item.discount_percent) ?? 0;
  const amount = parseAmount(item.discount_amount) ?? 0;
  if (percent > 0 && amount > 0) {
    ctx.addIssue({ code: 'custom', message: 'Use percent or amount, not both', path: ['discount_percent'] });
  }
}

function refineInvoiceDates(
  data: { issue_date: string; supply_date: string; due_date: string },
  ctx: z.RefinementCtx,
) {
  if (data.supply_date && data.issue_date && data.supply_date > data.issue_date) {
    ctx.addIssue({ code: 'custom', message: 'Supply date may not be after issue date', path: ['supply_date'] });
  }
  if (data.due_date && data.issue_date && data.due_date < data.issue_date) {
    ctx.addIssue({ code: 'custom', message: 'Due date must be on or after issue date', path: ['due_date'] });
  }
}

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

function localIso(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function todayIso(): string {
  return localIso(new Date());
}

function addDaysToIso(iso: string, days: number): string {
  const [year, month, day] = iso.split('-').map(Number);
  return localIso(new Date(year, (month ?? 1) - 1, (day ?? 1) + days));
}

function dueDateFromTerms(issueDate: string, termsDays: number | undefined): string {
  return addDaysToIso(issueDate || todayIso(), termsDays ?? 0);
}

function formatAed(value: string | number | null | undefined): string {
  return `AED ${Number(value ?? 0).toFixed(2)}`;
}

function emptyLine(): InvoiceFormValues['items'][number] {
  return {
    product_id: '',
    description: '',
    quantity: '1',
    unit_price: '',
    tax_rate: '',
    discount_percent: '',
    discount_amount: '',
  };
}

function blankInvoiceForm(): InvoiceFormValues {
  const issue = todayIso();
  return {
    client_id: '',
    issue_date: issue,
    supply_date: issue,
    due_date: issue,
    items: [emptyLine()],
  };
}

function lineToForm(item: InvoiceItem): InvoiceFormValues['items'][number] {
  const pct = Number(item.discount_percent ?? 0);
  const amt = Number(item.discount_amount ?? 0);
  return {
    product_id: item.product_id ?? '',
    description: item.description ?? '',
    quantity: String(item.quantity ?? 1),
    unit_price: String(item.unit_price ?? 0),
    tax_rate: item.tax_rate == null ? '' : String(item.tax_rate),
    discount_percent: pct > 0 ? String(item.discount_percent) : '',
    discount_amount: amt > 0 ? String(item.discount_amount) : '',
  };
}

function invoiceToForm(invoice: Invoice): InvoiceFormValues {
  return {
    client_id: invoice.client_id,
    issue_date: invoice.issue_date,
    supply_date: invoice.supply_date || invoice.issue_date,
    due_date: invoice.due_date,
    items: (invoice.items ?? []).map(lineToForm),
  };
}

function buildLinePayload(item: InvoiceFormValues['items'][number]): InvoiceItemWrite {
  const line: InvoiceItemWrite = { quantity: Number(item.quantity) };
  const productId = item.product_id?.trim();
  if (productId) line.product_id = productId;
  const description = item.description?.trim();
  if (description) line.description = description;
  const unitPrice = parseAmount(item.unit_price);
  if (unitPrice !== undefined) line.unit_price = unitPrice;
  const taxRate = parseAmount(item.tax_rate);
  if (taxRate !== undefined) line.tax_rate = taxRate;
  const percent = parseAmount(item.discount_percent);
  if (percent && percent > 0) line.discount_percent = percent;
  const amount = parseAmount(item.discount_amount);
  if (amount && amount > 0) line.discount_amount = amount;
  return line;
}

function buildCreatePayload(data: InvoiceFormValues): InvoiceCreatePayload {
  return {
    client_id: data.client_id,
    issue_date: data.issue_date,
    supply_date: data.supply_date,
    due_date: data.due_date,
    currency: 'AED',
    items: data.items.map(buildLinePayload),
  };
}

function buildUpdatePayload(data: InvoiceFormValues): InvoiceUpdatePayload {
  return {
    issue_date: data.issue_date,
    supply_date: data.supply_date,
    due_date: data.due_date,
    currency: 'AED',
    items: data.items.map(buildLinePayload),
  };
}

export const Invoices = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingInvoice, setEditingInvoice] = useState<Invoice | null>(null);
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [paymentInvoice, setPaymentInvoice] = useState<InvoiceListItem | null>(null);
  const [paymentAmount, setPaymentAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('BANK_TRANSFER');
  const [referenceNumber, setReferenceNumber] = useState('');
  const [bankName, setBankName] = useState('');
  const [pdcDate, setPdcDate] = useState('');
  const [pdfBusyId, setPdfBusyId] = useState<string | null>(null);
  const [previewInvoice, setPreviewInvoice] = useState<Invoice | null>(null);
  const [arInvoiceId, setArInvoiceId] = useState<string | null>(null);
  const [sendBlock, setSendBlock] = useState<{ code: string; message: string } | null>(null);

  const { data: invoices, isLoading } = useQuery({ queryKey: ['invoices'], queryFn: getInvoices });
  const { data: clients } = useQuery({ queryKey: ['clients'], queryFn: getClients });
  const { data: workspace } = useQuery({ queryKey: ['workspace'], queryFn: getCurrentWorkspace });
  const { data: productPage } = useQuery({
    queryKey: ['products', 'invoice-picker'],
    queryFn: () => getProducts({ page: 1, per_page: PRODUCT_PAGE_SIZE, is_active: true }),
  });

  const paymentMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: PaymentData }) => recordPayment(id, data),
    onSuccess: (payment) => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      queryClient.invalidateQueries({ queryKey: ['invoice'] });
      queryClient.invalidateQueries({ queryKey: ['invoice-payments'] });
      toast.success(paymentRecordedMessage(payment));
      setIsPaymentModalOpen(false);
      setPaymentInvoice(null);
      setPaymentAmount('');
      setPaymentMethod('BANK_TRANSFER');
      setReferenceNumber('');
      setBankName('');
      setPdcDate('');
    },
  });

  const createMutation = useMutation({
    mutationFn: createInvoice,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      closeModal();
      toast.success('Invoice created');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: InvoiceUpdatePayload }) => updateInvoice(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      closeModal();
      toast.success('Invoice updated');
    },
  });

  const actionMutation = useMutation({
    mutationFn: ({ id, action, payload }: { id: string; action: 'send' | 'void'; payload?: { reason?: string } }) =>
      action === 'send' ? sendInvoice(id) : voidInvoice(id, payload?.reason || 'Cancelled'),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      if (variables.action === 'send') setSendBlock(null);
      toast.success(`Invoice ${variables.action === 'send' ? 'sent' : 'voided'}`);
    },
    onError: (error: unknown) => {
      const parsed = extractApiError(error);
      if (parsed.code === 'FTA_SEND_BLOCKED' || parsed.code === 'CREDIT_HOLD') {
        setSendBlock({ code: parsed.code, message: parsed.message });
        toast.error(parsed.message);
      }
    },
  });

  const { register, control, handleSubmit, reset, setValue, watch, formState: { errors } } = useForm<InvoiceFormValues>({
    resolver: zodResolver(invoiceSchema),
    defaultValues: blankInvoiceForm(),
  });
  const selectedClientId = watch('client_id');
  const issueDate = watch('issue_date');

  useEffect(() => {
    if (!isModalOpen || editingInvoice) return;
    const terms = clients?.find((entry) => entry.id === selectedClientId)?.payment_terms_days;
    setValue('due_date', dueDateFromTerms(issueDate, terms));
  }, [isModalOpen, editingInvoice, selectedClientId, issueDate, clients, setValue]);

  const { fields, append, remove } = useFieldArray({ control, name: 'items' });

  const openModal = async (row?: InvoiceListItem) => {
    if (!row) {
      setEditingInvoice(null);
      reset(blankInvoiceForm());
      setIsModalOpen(true);
      return;
    }
    try {
      const full = await getInvoice(row.id);
      if (full.status !== 'DRAFT') {
        toast.error('Only draft invoices can be edited');
        return;
      }
      setEditingInvoice(full);
      reset(invoiceToForm(full));
      setIsModalOpen(true);
    } catch {
      return;
    }
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingInvoice(null);
  };

  const onSubmit = (data: InvoiceFormValues) => {
    if (editingInvoice) {
      updateMutation.mutate({ id: editingInvoice.id, data: buildUpdatePayload(data) });
    } else {
      createMutation.mutate(buildCreatePayload(data));
    }
  };

  const handleProductPick = async (index: number, productId: string) => {
    setValue(`items.${index}.product_id`, productId);
    if (!productId) return;
    const match = productPage?.items.find((product) => product.id === productId);
    if (match?.name) setValue(`items.${index}.description`, match.name);
    try {
      const prices = await getProductPrices(productId);
      const list = prices.find((price) => price.price_type === 'DEFAULT_SALES');
      if (list) setValue(`items.${index}.unit_price`, String(list.price));
    } catch {
      return;
    }
  };

  const openPdfPreview = async (row: InvoiceListItem) => {
    try {
      setPreviewInvoice(await getInvoice(row.id));
    } catch {
      return;
    }
  };

  const downloadPdf = async (row: InvoiceListItem) => {
    setPdfBusyId(row.id);
    try {
      const invoice = await getInvoice(row.id);
      const client = clients?.find((entry) => entry.id === invoice.client_id);
      const blob = await pdf(
        <InvoicePDF invoice={invoice} client={client} workspace={workspace} />,
      ).toBlob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `TaxInvoice_${invoice.invoice_number}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      const axiosError = error as { response?: unknown };
      if (!axiosError.response) toast.error('Could not generate tax invoice PDF');
    } finally {
      setPdfBusyId(null);
    }
  };

  const getStatusBadge = (status: InvoiceStatus) => {
    const map = {
      DRAFT: styles.badgeDraft,
      SENT: styles.badgeSent,
      PARTIALLY_PAID: styles.badgePartial,
      OVERDUE: styles.badgeOverdue,
      PAID: styles.badgePaid,
      CANCELLED: styles.badgeCancelled,
    };
    return <span className={`${styles.badge} ${map[status]}`}>{status.replace('_', ' ')}</span>;
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Invoices</h2>
        <button
          className={styles.primaryBtn}
          data-testid="invoice-create"
          onClick={() => openModal()}
        >
          <Plus size={16} style={{ display: 'inline', marginRight: '0.5rem', verticalAlign: 'middle' }} />
          Create Invoice
        </button>
      </div>

      {sendBlock && (
        <div
          className={styles.ftaBanner}
          data-testid={sendBlock.code === 'FTA_SEND_BLOCKED' ? 'fta-send-blocked' : 'credit-hold'}
          role="alert"
        >
          {sendBlock.message}
        </div>
      )}

      <div className={styles.tableContainer}>
        {isLoading ? (
          <div style={{ padding: '2rem' }}>
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} height="40px" style={{ marginBottom: '1rem' }} />
            ))}
          </div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Invoice #</th>
                <th>Client</th>
                <th>Status</th>
                <th>Total</th>
                <th>Paid (cash)</th>
                <th>Credited</th>
                <th>Amount Due</th>
                <th>Issue Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {invoices?.map((inv) => {
                const client = clients?.find((entry) => entry.id === inv.client_id);
                const amountDue = Number(inv.balance_due ?? 0);
                const showCredited = inv.amount_credited !== undefined && inv.amount_credited !== null;
                return (
                  <tr key={inv.id} data-testid={`invoice-row-${inv.invoice_number}`}>
                    <td>
                      <button
                        type="button"
                        className={styles.actionBtn}
                        style={{ fontWeight: 700, color: '#2563eb' }}
                        data-testid={`invoice-open-${inv.invoice_number}`}
                        onClick={() => setArInvoiceId(inv.id)}
                      >
                        {inv.invoice_number}
                      </button>
                    </td>
                    <td>{client?.name || 'Unknown Client'}</td>
                    <td data-testid="invoice-status">{getStatusBadge(inv.status)}</td>
                    <td>{formatAed(inv.total_amount)}</td>
                    <td data-testid="invoice-amount-paid">{formatAed(inv.amount_paid)}</td>
                    <td data-testid="invoice-amount-credited">
                      {showCredited ? formatAed(inv.amount_credited) : '—'}
                    </td>
                    <td data-testid="invoice-balance-due">{formatAed(amountDue)}</td>
                    <td>{new Date(inv.issue_date).toLocaleDateString()}</td>
                    <td>
                      <button
                        className={styles.actionBtn}
                        data-testid="invoice-preview-pdf"
                        onClick={() => void openPdfPreview(inv)}
                        title="Preview tax invoice"
                      >
                        <Eye size={16} />
                      </button>
                      <button
                        className={styles.actionBtn}
                        data-testid="invoice-download-pdf"
                        onClick={() => downloadPdf(inv)}
                        disabled={pdfBusyId === inv.id}
                        title="Download tax invoice PDF"
                      >
                        <Download size={16} />
                      </button>
                      {inv.status === 'DRAFT' && (
                        <>
                          <button className={styles.actionBtn} onClick={() => openModal(inv)} title="Edit">
                            <Edit2 size={16} />
                          </button>
                          <button
                            className={styles.actionBtn}
                            data-testid="invoice-send"
                            onClick={() => actionMutation.mutate({ id: inv.id, action: 'send' })}
                            title={
                              client?.credit_status === 'HOLD'
                                ? 'Blocked while this client is on credit HOLD'
                                : 'Mark as Sent'
                            }
                          >
                            <Send size={16} />
                          </button>
                          <button
                            className={styles.actionBtn}
                            onClick={() => {
                              const reason = window.prompt('Reason for voiding? (min 5 chars)');
                              if (reason && reason.length >= 5) {
                                actionMutation.mutate({ id: inv.id, action: 'void', payload: { reason } });
                              } else if (reason) {
                                alert('Reason must be at least 5 characters');
                              }
                            }}
                            title="Void"
                          >
                            <XCircle size={16} />
                          </button>
                        </>
                      )}
                      {(inv.status === 'SENT' || inv.status === 'PARTIALLY_PAID' || inv.status === 'OVERDUE') && (
                        <button
                          className={styles.actionBtn}
                          data-testid="invoice-record-payment"
                          onClick={() => {
                            setPaymentInvoice(inv);
                            setPaymentAmount(Number(amountDue ?? 0).toFixed(2));
                            setIsPaymentModalOpen(true);
                          }}
                          title="Record Payment"
                        >
                          <DollarSign size={16} />
                        </button>
                      )}
                      {isCreditableStatus(inv.status) && (
                        <button
                          className={styles.actionBtn}
                          data-testid="invoice-create-cn"
                          onClick={() => navigate(`/credit-notes/new?invoice_id=${inv.id}`)}
                          title="Create tax credit note"
                        >
                          <FileMinus size={16} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {invoices?.length === 0 && (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: '2rem' }}>No invoices found.</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {isModalOpen && (
        <div className={styles.modalOverlay} data-testid="invoice-modal">
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <h3>{editingInvoice ? 'Edit Invoice' : 'Create Invoice'}</h3>
              <button className={styles.closeBtn} onClick={closeModal}>&times;</button>
            </div>
            <form onSubmit={handleSubmit(onSubmit)}>
              <div className={styles.grid2}>
                <div className={styles.formGroup}>
                  <label>Client</label>
                  <select
                    data-testid="invoice-client-select"
                    {...register('client_id')}
                    disabled={Boolean(editingInvoice)}
                  >
                    <option value="">Select a client...</option>
                    {clients?.map((client) => (
                      <option key={client.id} value={client.id}>{client.name}</option>
                    ))}
                  </select>
                  {errors.client_id && <span className={styles.errorText}>{errors.client_id.message}</span>}
                  {clients?.find((entry) => entry.id === selectedClientId)?.credit_status === 'HOLD' && (
                    <span className={styles.hint}>
                      This client is on credit HOLD. Send will be blocked until exposure or overdue is cleared.
                    </span>
                  )}
                </div>
                <div className={styles.formGroup}>
                  <label>Currency</label>
                  <span className={styles.currencyLabel}>AED</span>
                </div>
                <div className={styles.formGroup}>
                  <label>Issue Date</label>
                  <input type="date" data-testid="invoice-issue-date" {...register('issue_date')} />
                  {errors.issue_date && <span className={styles.errorText}>{errors.issue_date.message}</span>}
                </div>
                <div className={styles.formGroup}>
                  <label>Supply Date</label>
                  <input type="date" data-testid="invoice-supply-date" {...register('supply_date')} />
                  <span className={styles.hint}>Defaults to issue date. Cannot be after issue date.</span>
                  {errors.supply_date && <span className={styles.errorText}>{errors.supply_date.message}</span>}
                </div>
                <div className={styles.formGroup}>
                  <label>Due Date</label>
                  <input type="date" data-testid="invoice-due-date" {...register('due_date')} />
                  {errors.due_date && <span className={styles.errorText}>{errors.due_date.message}</span>}
                </div>
              </div>

              <div className={styles.itemsSection}>
                <div className={styles.itemsHeader}>
                  <h4>Line Items</h4>
                  <button type="button" className={styles.secondaryBtn} onClick={() => append(emptyLine())}>
                    Add Item
                  </button>
                </div>
                {fields.map((field, index) => {
                  const productField = register(`items.${index}.product_id` as const);
                  return (
                  <div key={field.id} className={styles.itemRow}>
                    <div className={styles.itemRowMain}>
                      <div className={styles.formGroup}>
                        <label>Product (optional)</label>
                        <select
                          data-testid={`invoice-item-${index}-product`}
                          {...productField}
                          onChange={(event) => {
                            void productField.onChange(event);
                            void handleProductPick(index, event.target.value);
                          }}
                        >
                          <option value="">Ad-hoc (name / qty / price)</option>
                          {productPage?.items.map((product) => (
                            <option key={product.id} value={product.id}>
                              {product.internal_sku} — {product.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className={styles.formGroup}>
                        <label>Description</label>
                        <input
                          data-testid={`invoice-item-${index}-description`}
                          {...register(`items.${index}.description` as const)}
                        />
                        {errors.items?.[index]?.description && (
                          <span className={styles.errorText}>{errors.items[index].description.message}</span>
                        )}
                      </div>
                    </div>
                    <div className={styles.itemRowNums}>
                      <div className={styles.formGroup}>
                        <label>Qty</label>
                        <input
                          type="number"
                          step="0.01"
                          data-testid={`invoice-item-${index}-quantity`}
                          {...register(`items.${index}.quantity` as const)}
                        />
                        {errors.items?.[index]?.quantity && (
                          <span className={styles.errorText}>{errors.items[index].quantity.message}</span>
                        )}
                      </div>
                      <div className={styles.formGroup}>
                        <label>Price (AED)</label>
                        <input
                          type="number"
                          step="0.01"
                          data-testid={`invoice-item-${index}-price`}
                          {...register(`items.${index}.unit_price` as const)}
                        />
                        {errors.items?.[index]?.unit_price && (
                          <span className={styles.errorText}>{errors.items[index].unit_price.message}</span>
                        )}
                      </div>
                      <div className={styles.formGroup}>
                        <label>Disc %</label>
                        <input
                          type="number"
                          step="0.01"
                          data-testid={`invoice-item-${index}-discount-percent`}
                          {...register(`items.${index}.discount_percent` as const)}
                        />
                        {errors.items?.[index]?.discount_percent && (
                          <span className={styles.errorText}>{errors.items[index].discount_percent.message}</span>
                        )}
                      </div>
                      <div className={styles.formGroup}>
                        <label>Disc AED</label>
                        <input type="number" step="0.01" {...register(`items.${index}.discount_amount` as const)} />
                      </div>
                      <div className={styles.formGroup}>
                        <label>VAT %</label>
                        <input
                          type="number"
                          step="0.01"
                          placeholder="Inherit"
                          data-testid={`invoice-item-${index}-tax`}
                          {...register(`items.${index}.tax_rate` as const)}
                        />
                        <span className={styles.hint}>Blank inherits 5% (or product rate).</span>
                        {errors.items?.[index]?.tax_rate && (
                          <span className={styles.errorText}>{errors.items[index].tax_rate.message}</span>
                        )}
                      </div>
                      <button
                        type="button"
                        className={styles.removeBtn}
                        onClick={() => remove(index)}
                        disabled={fields.length === 1}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                  );
                })}
                {errors.items?.root && <span className={styles.errorText}>{errors.items.root.message}</span>}
                {errors.items?.message && <span className={styles.errorText}>{errors.items.message}</span>}
              </div>

              <div className={styles.modalActions}>
                <button type="button" className={styles.secondaryBtn} onClick={closeModal}>Cancel</button>
                <button
                  type="submit"
                  className={styles.primaryBtn}
                  data-testid="invoice-form-submit"
                  disabled={createMutation.isPending || updateMutation.isPending}
                >
                  {editingInvoice ? 'Update Invoice' : 'Create Invoice'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {isPaymentModalOpen && paymentInvoice && (
        <div className={styles.modalOverlay}>
          <div className={styles.modal} style={{ maxWidth: '500px' }}>
            <div className={styles.modalHeader}>
              <h3>Record Payment</h3>
              <button className={styles.closeBtn} onClick={() => setIsPaymentModalOpen(false)}>&times;</button>
            </div>
            <div className={styles.formGroup} style={{ marginTop: '1rem' }}>
              <label>Amount (AED)</label>
              <input
                type="number"
                step="0.01"
                data-testid="payment-amount"
                value={paymentAmount}
                onChange={(e) => setPaymentAmount(e.target.value)}
              />
            </div>
            <div className={styles.formGroup}>
              <label>Payment Method</label>
              <select
                data-testid="payment-method"
                value={paymentMethod}
                onChange={(e) => setPaymentMethod(e.target.value)}
              >
                <option value="BANK_TRANSFER">Bank Transfer</option>
                <option value="CASH">Cash</option>
                <option value="CREDIT_CARD">Credit Card</option>
                <option value="CHEQUE">Cheque (cleared on receipt)</option>
                <option value="PDC">Post-Dated Cheque (PDC)</option>
              </select>
            </div>

            {(paymentMethod === 'CHEQUE' || paymentMethod === 'PDC' || paymentMethod === 'BANK_TRANSFER') && (
              <div className={styles.formGroup}>
                <label>{paymentMethod === 'BANK_TRANSFER' ? 'Transaction Ref' : 'Cheque Number'}</label>
                <input type="text" value={referenceNumber} onChange={(e) => setReferenceNumber(e.target.value)} />
              </div>
            )}

            {(paymentMethod === 'CHEQUE' || paymentMethod === 'PDC') && (
              <div className={styles.formGroup}>
                <label>Bank Name</label>
                <input type="text" value={bankName} onChange={(e) => setBankName(e.target.value)} />
              </div>
            )}

            {paymentMethod === 'PDC' && (
              <div className={styles.formGroup}>
                <label htmlFor="payment-pdc-date">Cheque date</label>
                <input
                  id="payment-pdc-date"
                  type="date"
                  data-testid="payment-pdc-date"
                  value={pdcDate}
                  onChange={(e) => setPdcDate(e.target.value)}
                  required
                />
                <span className={styles.hint}>
                  Uncleared PDC is pending, not cash. Use Cheque for one-step SUCCESS.
                </span>
              </div>
            )}

            <div className={styles.modalActions}>
              <button type="button" className={styles.secondaryBtn} onClick={() => setIsPaymentModalOpen(false)}>Cancel</button>
              <button
                type="button"
                className={styles.primaryBtn}
                data-testid="payment-submit"
                disabled={
                  paymentMutation.isPending ||
                  !paymentAmount ||
                  (paymentMethod === 'PDC' && !pdcDate)
                }
                onClick={() => {
                  if (paymentMethod === 'PDC' && !pdcDate) {
                    toast.error('Cheque date is required for PDC');
                    return;
                  }
                  const data: PaymentData = {
                    amount: parseFloat(paymentAmount),
                    payment_method: paymentMethod,
                  };
                  if (referenceNumber) data.reference_number = referenceNumber;
                  if (bankName) data.bank_name = bankName;
                  if (paymentMethod === 'PDC') data.pdc_date = pdcDate;
                  paymentMutation.mutate({ id: paymentInvoice.id, data });
                }}
              >
                {paymentMutation.isPending ? 'Recording...' : 'Record Payment'}
              </button>
            </div>
          </div>
        </div>
      )}

      {previewInvoice && (
        <InvoicePdfPreview
          invoice={previewInvoice}
          client={clients?.find((entry) => entry.id === previewInvoice.client_id)}
          workspace={workspace}
          onClose={() => setPreviewInvoice(null)}
        />
      )}

      {arInvoiceId && (
        <InvoiceArPanel invoiceId={arInvoiceId} onClose={() => setArInvoiceId(null)} />
      )}
    </div>
  );
};
