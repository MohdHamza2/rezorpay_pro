# Roadmap

> **Authoritative wave numbering.** This file is the source of truth for phase/wave
> numbering. `.agents/MASTER_PLAN_V3.md` uses a **superseded** sequence (its Wave 26 =
> WhatsApp, Wave 28 = India) — treat it as history, not roadmap. Committed sequence:
> Waves 21–25 = Phase 4 (AP Payments & Aging), Waves 26–28 = Phase 5 (Communications &
> Integrations), Wave 29 = Phase 6 (Reporting & Dashboard).

## Phase 1: Tax Debit Notes (Sales)
- WP-A: API, Alembic, tests
- WP-B: UI + PDF
- WP-C: Playwright E2E

## Phase 2: Enquiry Management (Wave 7)
- Pre-sales enquiry logging, tracking, and conversion to Quotation.

## Phase 3: Advanced Inventory (Waves 18-19)
- Stock Reservations based on Customer POs.
- Multi-warehouse Stock Transfers and Stock Counting/Reconciliation.

## Phase 4: AP Payments & Aging (Waves 21-25)
- Supplier payment recording.
- AP aging reports and integration with the supplier invoice matching engine.
- Wave 22: supplier AP payments + aging + generated supplier statement.
- Wave 23: purchase returns + supplier debit notes (AP).
- Wave 24: PDC-to-supplier (AP post-dated cheque lifecycle).
- Wave 25: AP payment reversal (bank bounce SUCCESS -> FAILED).

## Phase 5: Communications & Integrations (Waves 26-28)
- Wave 26: Email Engine via Resend API.
- Wave 27: WhatsApp Business API (Meta) integration for automated PDF delivery.
- Wave 28: UAE VAT Compliance Pack export.
- India-market rules (Category 11 in `business-rules.md`) are a **deferred market wave** — not part of Phase 5.

## Phase 6: Reporting & Dashboard (Wave 29)
- AR/AP aging UI, VAT compliance export view, dashboard enhancements.
- Playwright E2E for Reports/Dashboard still pending (AUDIT.md item 1.4).
