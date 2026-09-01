import { useCallback, useRef, useState } from 'react';
import { getResolvedPrice } from '../api/products';
import { isHttpNotFound } from '../api/errors';

export type PriceSourceLabel = 'List' | 'Volume' | 'Customer' | 'Override';

export type CatalogLineSnapshot = {
  product_id?: string;
  quantity: string;
};

export type CatalogLinePricingArgs = {
  fieldIds: string[];
  getClientId: () => string | undefined;
  getLine: (index: number) => CatalogLineSnapshot;
  setUnitPrice: (index: number, value: string) => void;
  setDescription?: (index: number, value: string) => void;
  productName?: (productId: string) => string | undefined;
};

export function labelForPriceType(priceType: string): Exclude<PriceSourceLabel, 'Override'> {
  if (priceType === 'TIER_1') return 'Volume';
  if (priceType === 'CUSTOMER_SPECIFIC') return 'Customer';
  return 'List';
}

export function previewQuantity(raw: string | undefined): string | null {
  if (raw == null || raw.trim() === '') return null;
  const qty = Number(raw);
  if (!Number.isFinite(qty) || qty <= 0) return null;
  return raw.trim();
}

export function formatResolvedUnitPrice(value: string | number): string {
  return Number(value ?? 0).toFixed(2);
}

function catalogProductId(raw: string | undefined): string | null {
  const id = raw?.trim();
  return id ? id : null;
}

function nextSeq(seq: Record<string, number>, fieldId: string): number {
  const next = (seq[fieldId] ?? 0) + 1;
  seq[fieldId] = next;
  return next;
}

export function LinePriceSource({
  testId,
  source,
  className,
}: {
  testId: string;
  source?: PriceSourceLabel;
  className: string;
}) {
  if (!source) return null;
  return (
    <span className={className} data-testid={testId}>
      {source}
    </span>
  );
}

type PreviewOverrides = {
  clientId?: string;
  quantity?: string;
  productId?: string;
};

export function useCatalogLinePricing(args: CatalogLinePricingArgs) {
  const argsRef = useRef(args);
  argsRef.current = args;
  const dirtyRef = useRef<Record<string, boolean>>({});
  const seqRef = useRef<Record<string, number>>({});
  const [sources, setSources] = useState<Record<string, PriceSourceLabel | ''>>({});

  const setSource = (fieldId: string, source: PriceSourceLabel | '') => {
    setSources((prev) => (prev[fieldId] === source ? prev : { ...prev, [fieldId]: source }));
  };

  const applyResolved = (fieldId: string, price: string, source: PriceSourceLabel) => {
    const index = argsRef.current.fieldIds.indexOf(fieldId);
    if (index < 0 || dirtyRef.current[fieldId]) return;
    argsRef.current.setUnitPrice(index, price);
    setSource(fieldId, source);
  };

  const clearStalePrice = (fieldId: string) => {
    const index = argsRef.current.fieldIds.indexOf(fieldId);
    if (index < 0 || dirtyRef.current[fieldId]) return;
    argsRef.current.setUnitPrice(index, '');
    setSource(fieldId, '');
  };

  const runPreview = async (
    fieldId: string,
    productId: string,
    quantity: string,
    clientId: string | undefined,
    seq: number,
  ) => {
    try {
      const resolved = await getResolvedPrice(productId, {
        quantity,
        client_id: clientId?.trim() || undefined,
      });
      if (seqRef.current[fieldId] !== seq) return;
      applyResolved(
        fieldId,
        formatResolvedUnitPrice(resolved.unit_price),
        labelForPriceType(resolved.price_type),
      );
    } catch (error) {
      if (seqRef.current[fieldId] !== seq) return;
      clearStalePrice(fieldId);
      if (isHttpNotFound(error)) return;
    }
  };

  const resolveRef = useRef<(index: number, overrides?: PreviewOverrides) => void>(() => {});
  resolveRef.current = (index, overrides) => {
    const fieldId = argsRef.current.fieldIds[index];
    if (!fieldId) return;
    const line = argsRef.current.getLine(index);
    const productId = catalogProductId(overrides?.productId ?? line.product_id);
    const quantity = previewQuantity(overrides?.quantity ?? line.quantity);
    if (!productId || !quantity || dirtyRef.current[fieldId]) return;
    const seq = nextSeq(seqRef.current, fieldId);
    const clientId = overrides?.clientId ?? argsRef.current.getClientId();
    void runPreview(fieldId, productId, quantity, clientId, seq);
  };

  const onProductPick = useCallback((index: number, productId: string) => {
    const fieldId = argsRef.current.fieldIds[index];
    if (!fieldId) return;
    dirtyRef.current[fieldId] = false;
    setSource(fieldId, '');
    const id = catalogProductId(productId);
    if (!id) return;
    const name = argsRef.current.productName?.(id);
    if (name) argsRef.current.setDescription?.(index, name);
    resolveRef.current(index, { productId: id });
  }, []);

  const onQuantityChange = useCallback((index: number, quantity: string) => {
    resolveRef.current(index, { quantity });
  }, []);

  const onPriceInput = useCallback((index: number) => {
    const fieldId = argsRef.current.fieldIds[index];
    if (!fieldId) return;
    if (!catalogProductId(argsRef.current.getLine(index).product_id)) return;
    dirtyRef.current[fieldId] = true;
    nextSeq(seqRef.current, fieldId);
    setSource(fieldId, 'Override');
  }, []);

  const onHeaderClientChange = useCallback((clientId: string) => {
    argsRef.current.fieldIds.forEach((_, index) => {
      resolveRef.current(index, { clientId });
    });
  }, []);

  const sourceFor = (index: number): PriceSourceLabel | undefined => {
    const id = args.fieldIds[index];
    const source = id ? sources[id] : undefined;
    return source || undefined;
  };

  return { sourceFor, onProductPick, onQuantityChange, onPriceInput, onHeaderClientChange };
}
