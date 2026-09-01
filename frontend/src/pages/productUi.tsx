import type { ReactNode } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { Skeleton } from '../components/Skeleton';
import type { ProductListQuery, ProductWrite } from '../api/products';
import type { PaginationMeta } from '../types/api';
import styles from './Products.module.css';

export const VOLTAGE_PATTERN = /^[0-9]+(\/[0-9]+)?$/;

export type ProductSpecFilterValues = {
  amp_rating: string;
  cable_size_mm2: string;
  cores: string;
  poles: string;
  voltage: string;
};

export const EMPTY_PRODUCT_SPEC_FILTERS: ProductSpecFilterValues = {
  amp_rating: '',
  cable_size_mm2: '',
  cores: '',
  poles: '',
  voltage: '',
};

type SpecFormSlice = {
  amp_rating?: string;
  cable_size_mm2?: string;
  cores?: string;
  poles?: string;
  voltage?: string;
};

type SpecDisplay = {
  amp_rating?: string | number | null;
  cable_size_mm2?: string | number | null;
  cores?: number | null;
  poles?: number | null;
  voltage?: string | null;
};

export function formatAed(amount: string | number | null | undefined): string {
  return `AED ${Number(amount ?? 0).toFixed(2)}`;
}

export function formatFactor(value: string | number | null | undefined): string {
  const n = Number(value ?? 0);
  return Number.isNaN(n) ? '0' : String(n);
}

export function optionalId(value: string | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

export function optionalAmount(value: string | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

export function optionalInt(value: string | undefined): number | null {
  const trimmed = value?.trim();
  if (!trimmed) return null;
  return Number.parseInt(trimmed, 10);
}

export function stripTrailingZeros(value: string | number): string {
  const raw = String(value).trim();
  if (!raw.includes('.')) return raw;
  return raw.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
}

export function specFieldValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '';
  return stripTrailingZeros(value);
}

function hasSpec(value: string | number | null | undefined): boolean {
  return value !== null && value !== undefined && String(value).trim() !== '';
}

export function formatProductSpecs(product: SpecDisplay): string {
  const parts: string[] = [];
  if (hasSpec(product.cores) && hasSpec(product.cable_size_mm2)) {
    parts.push(`${product.cores}C ${stripTrailingZeros(String(product.cable_size_mm2))}mm²`);
  }
  if (hasSpec(product.amp_rating) && hasSpec(product.poles)) {
    parts.push(`${stripTrailingZeros(String(product.amp_rating))}A ${product.poles}P`);
  }
  const body = parts.join(' ');
  if (!product.voltage) return body || '—';
  return body ? `${body} ${product.voltage}V` : `${product.voltage}V`;
}

export function pickSpecCreate(values: SpecFormSlice): Partial<ProductWrite> {
  const payload: Partial<ProductWrite> = {};
  const amp = optionalAmount(values.amp_rating);
  if (amp) payload.amp_rating = amp;
  const mm2 = optionalAmount(values.cable_size_mm2);
  if (mm2) payload.cable_size_mm2 = mm2;
  const cores = optionalInt(values.cores);
  if (cores !== null) payload.cores = cores;
  const poles = optionalInt(values.poles);
  if (poles !== null) payload.poles = poles;
  const voltage = values.voltage?.trim();
  if (voltage) payload.voltage = voltage;
  return payload;
}

export function pickSpecUpdate(values: SpecFormSlice): Partial<ProductWrite> {
  const voltage = values.voltage?.trim();
  return {
    amp_rating: optionalAmount(values.amp_rating),
    cable_size_mm2: optionalAmount(values.cable_size_mm2),
    cores: optionalInt(values.cores),
    poles: optionalInt(values.poles),
    voltage: voltage || null,
  };
}

function parseFilterInt(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed || !/^\d+$/.test(trimmed)) return undefined;
  return Number.parseInt(trimmed, 10);
}

export function specFiltersToQuery(filters: ProductSpecFilterValues): ProductListQuery {
  const query: ProductListQuery = {};
  if (filters.amp_rating.trim()) query.amp_rating = filters.amp_rating.trim();
  if (filters.cable_size_mm2.trim()) query.cable_size_mm2 = filters.cable_size_mm2.trim();
  const cores = parseFilterInt(filters.cores);
  if (cores !== undefined) query.cores = cores;
  const poles = parseFilterInt(filters.poles);
  if (poles !== undefined) query.poles = poles;
  if (filters.voltage.trim()) query.voltage = filters.voltage.trim();
  return query;
}

export function isValidFilterVoltage(value: string): boolean {
  const trimmed = value.trim();
  return !trimmed || VOLTAGE_PATTERN.test(trimmed);
}

function SpecField({
  label,
  testId,
  register,
  error,
  placeholder,
}: {
  label: string;
  testId: string;
  register: UseFormRegisterReturn;
  error?: string;
  placeholder?: string;
}) {
  return (
    <div className={styles.formGroup}>
      <label>{label}</label>
      <input {...register} data-testid={testId} placeholder={placeholder} />
      {error && <span className={styles.errorText}>{error}</span>}
    </div>
  );
}

export function ProductSpecFormFields({
  amp,
  mm2,
  cores,
  poles,
  voltage,
  errors,
}: {
  amp: UseFormRegisterReturn;
  mm2: UseFormRegisterReturn;
  cores: UseFormRegisterReturn;
  poles: UseFormRegisterReturn;
  voltage: UseFormRegisterReturn;
  errors: { amp?: string; mm2?: string; cores?: string; poles?: string; voltage?: string };
}) {
  return (
    <>
      <p className={styles.hint}>Electrical specs are optional. Leave blank for accessories.</p>
      <div className={styles.formRow}>
        <SpecField label="Amp" testId="product-amp-input" register={amp} error={errors.amp} placeholder="63" />
        <SpecField
          label="Cable mm²"
          testId="product-mm2-input"
          register={mm2}
          error={errors.mm2}
          placeholder="10"
        />
      </div>
      <div className={styles.formRow}>
        <SpecField label="Cores" testId="product-cores-input" register={cores} error={errors.cores} placeholder="4" />
        <SpecField label="Poles" testId="product-poles-input" register={poles} error={errors.poles} placeholder="3" />
      </div>
      <SpecField
        label="Voltage"
        testId="product-voltage-input"
        register={voltage}
        error={errors.voltage}
        placeholder="230/400"
      />
    </>
  );
}

function FilterInput({
  label,
  testId,
  value,
  onChange,
  onApply,
  placeholder,
}: {
  label: string;
  testId: string;
  value: string;
  onChange: (value: string) => void;
  onApply: () => void;
  placeholder?: string;
}) {
  return (
    <label className={styles.filterField}>
      {label}
      <input
        data-testid={testId}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            onApply();
          }
        }}
      />
    </label>
  );
}

export function ProductSpecFilterBar({
  values,
  onChange,
  onApply,
  onClear,
}: {
  values: ProductSpecFilterValues;
  onChange: (next: ProductSpecFilterValues) => void;
  onApply: () => void;
  onClear: () => void;
}) {
  const set = (key: keyof ProductSpecFilterValues, value: string) =>
    onChange({ ...values, [key]: value });
  return (
    <div className={styles.filterBar}>
      <FilterInput
        label="Amp"
        testId="product-filter-amp"
        value={values.amp_rating}
        onChange={(value) => set('amp_rating', value)}
        onApply={onApply}
        placeholder="63"
      />
      <FilterInput
        label="Cable mm²"
        testId="product-filter-mm2"
        value={values.cable_size_mm2}
        onChange={(value) => set('cable_size_mm2', value)}
        onApply={onApply}
        placeholder="10"
      />
      <FilterInput
        label="Cores"
        testId="product-filter-cores"
        value={values.cores}
        onChange={(value) => set('cores', value)}
        onApply={onApply}
        placeholder="4"
      />
      <FilterInput
        label="Poles"
        testId="product-filter-poles"
        value={values.poles}
        onChange={(value) => set('poles', value)}
        onApply={onApply}
        placeholder="3"
      />
      <FilterInput
        label="Voltage"
        testId="product-filter-voltage"
        value={values.voltage}
        onChange={(value) => set('voltage', value)}
        onApply={onApply}
        placeholder="230/400"
      />
      <button type="button" className={styles.primaryBtn} data-testid="product-filter-apply" onClick={onApply}>
        Apply
      </button>
      <button type="button" className={styles.secondaryBtn} data-testid="product-filter-clear" onClick={onClear}>
        Clear
      </button>
    </div>
  );
}

export function confirmSoftDelete(entityLabel: string): boolean {
  return window.confirm(`Are you sure you want to delete this ${entityLabel}?`);
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div style={{ padding: '2rem' }}>
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} height="40px" style={{ marginBottom: '1rem' }} />
      ))}
    </div>
  );
}

export function PaginationBar({
  pagination,
  onPage,
}: {
  pagination?: PaginationMeta;
  onPage: (page: number) => void;
}) {
  if (!pagination || pagination.pages <= 1) return null;
  return (
    <div className={styles.pagination} data-testid="pagination-bar">
      <button
        type="button"
        className={styles.secondaryBtn}
        disabled={!pagination.has_prev}
        onClick={() => onPage(pagination.page - 1)}
      >
        Previous
      </button>
      <span>
        Page {pagination.page} of {pagination.pages}
      </span>
      <button
        type="button"
        className={styles.secondaryBtn}
        disabled={!pagination.has_next}
        onClick={() => onPage(pagination.page + 1)}
      >
        Next
      </button>
    </div>
  );
}

export function ProductModal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className={styles.modalOverlay} data-testid="catalog-modal">
      <div className={wide ? `${styles.modal} ${styles.modalWide}` : styles.modal}>
        <div className={styles.modalHeader}>
          <h3>{title}</h3>
          <button type="button" className={styles.closeBtn} onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
