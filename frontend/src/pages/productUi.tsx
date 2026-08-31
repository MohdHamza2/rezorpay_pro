import type { ReactNode } from 'react';
import { Skeleton } from '../components/Skeleton';
import type { PaginationMeta } from '../types/api';
import styles from './Products.module.css';

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
