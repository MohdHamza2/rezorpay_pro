# Architect note — Tax debit notes (sales FTA)

**Date:** 2026-09-01
**Code:** none. No Alembic files. No git commit.

**Addendum:** `architecture/wave-debit-notes-addendum.md`

## Coder-ready locks

| Lock | Value |
|---|---|
| Number | **`TDN-YYYY-XXXX`** gapless FOR UPDATE at create. Soft-delete does not rewind. **Not** `DN-YYYY-XXXX` (delivery notes). Not `DNTE-` / `DBN-`. |
| Alembic | **YES.** New revision only. **`down_revision = "1a30af047312"`**. Never rewrite specs/CN/DN/credit/LPO/FTA/AR/PDC/pricing/PDF history. |
| AR formula | `net_billed = total − amount_credited + amount_debited`; `balance_due = max(0, net_billed − paid)`; `credit_owing = max(0, −raw)`. Column `invoices.amount_debited` Numeric(12,2) default 0. Never negative payments. Never UPDATE/DELETE payment rows. |
| PAID + TDN | **Reopen** PARTIALLY_PAID (or OVERDUE) when `balance_due > 0`. Stay PAID only if debit is smaller than this invoice’s parked over-credit. Unpark `clients.credit_balance` by shrink of `credit_owing`. Do not auto-apply credit from other invoices. |
| HOLD | **Does not block** `POST /debit-notes/{id}/issue`. FTA correction of a SENT invoice, not a new send. Evaluate after; exposure rises. |
| Remaining | TDN: **unlimited undercharge** (qty > 0, frozen invoice prices, lines subset of invoice items). No cap vs invoice total. CN remaining **this WP**: `invoice qty/total + Σ ISSUED TDN − Σ ISSUED CN`. |
| State | DRAFT → ISSUED posts AR. No `/apply`. PUT/DELETE DRAFT only. Issue idempotent 200. MEMBER+ (mirror live CN, not T17 paper). Isolation **404**. |
| PDF | English **Tax Debit Note** + AR **إشعار مدين ضريبي** via `pdfTitles.ts`. testid `tdn-pdf-title`. Not Delivery Note / Tax Credit Note / Tax Invoice. |
| UI | `/debit-notes` under Sales **after Credit Notes**. Label **Debit Notes**. Do not sit next to Delivery Notes. |
| Out | Purchase AP debit notes, warehouse sales-return stock, Peppol, WhatsApp, mutating payments, rewriting DN. |

## Why this slice (not AP DN)

Gaps paper bunched “purchase returns / debit notes / sales return warehouse” as NOT-MVP and pointed sales returns at CN. CN is shipped. The remaining FTA path is **undercharge** on a tax invoice. Paper `DebitNote` is supplier AP with prefix `DN-` — collision with delivery notes and out of MVP.

## WP split

- **A** Models + Alembic from `1a30af047312` + issue posts AR + CN remaining + statement query + `test_debit_notes.py`. No frontend until pytest green.
- **B** `/debit-notes` UI + `TaxDebitNotePDF` + invoice AR `amount_debited`.
- **C** Playwright: SENT invoice → issue TDN → AR increases; isolation 404; PDF title Tax Debit Note. Docker 8000 / Postgres 5434 / Vite 5173. Never SQLite.

Next after A–C: e-invoice field pack / Peppol readiness. Not Peppol XML, WhatsApp inbox, `*_ar` party names, rewriting delivery notes.
