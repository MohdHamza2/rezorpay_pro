# RezorPay Graphify

## Overview

This repository ships a layered, regenerate-able Graphify documentation system for the
full RezorPay codebase (backend FastAPI app, frontend React app, Alembic migrations and
tests). Graphify scans the source code locally (AST + static analysis, no LLM required)
and emits a knowledge graph plus several human-friendly views.

Because the codebase contains **5,357 nodes** — more than Graphify's interactive-view
limit of 5,000 — no single view tries to render everything. Instead the system is split
into layers:

| Layer | Artifact | What it answers |
|---|---|---|
| High-level overview | `graph.html` | What are the ~197 subsystems / communities, and how do they connect? |
| Project hierarchy | `GRAPH_TREE.html` | Where do files live in `backend/` and `frontend/`? |
| Architecture | `rezorpay_pro-callflow.html` | How does a request flow through Router → Service → Model → DB? |
| Domain detail | `subgraphs/*.html` | Focused interactive graphs per subsystem. |
| Complete detail | `full-detail.html` | All 5,357 nodes for deep investigation / debugging. |
| Raw data | `graph.json` | The machine-readable graph (source of every view above). |

Everything in `graphify-out/` is generated output. You can regenerate all of it with one
helper script (see "How to regenerate").

## Files

| File | Type | Description |
|---|---|---|
| `graph.html` | Interactive graph | Aggregated **community overview**: 197 community nodes and their 879 cross-community edges, labelled with deterministic hub names (e.g. `ProductService`, `App.tsx`). No LLM was used for the labels. |
| `GRAPH_TREE.html` | Interactive tree | D3 collapsible **file/directory hierarchy** built from `graph.json`. Expand folders, search, see how many symbols each file contributes. |
| `rezorpay_pro-callflow.html` | Static-ish pages | Mermaid-based **architecture & call-flow** documentation: the project import/call topology, per-subsystem call tables and diagram sections. |
| `full-detail.html` | Interactive graph | The **full detailed graph**: all 5,357 nodes / 19,367 edges with a search box, legend, node inspector and community filter. Large (~7 MB) — open on demand. |
| `graph.json` | JSON data | The **canonical detailed graph** (node-link format). Every other file here is derived from it. |
| `GRAPH_REPORT.md` | Markdown | Graphify's own text report: communities, hubs, god nodes, cohesion. |
| `.graphify_analysis.json` | JSON | Clustering sidecar (community → member lists, cohesion, god nodes). |
| `.graphify_labels.json` | JSON | 197 deterministic community labels (hub-based) used by every view. |
| `subgraphs/` | HTML | Focused subsystem graphs (see below). |

`subgraphs/` contains:

| File | Focus |
|---|---|
| `inventory.html` | Stock transfers, reservations, counts, inventory adjustments, landed cost |
| `procurement-requests.html` | Procurement requests (PPR), enquiries, RFQ + awards |
| `supplier-purchase-orders.html` | Supplier purchase orders (SPO), amendments, GRN |
| `purchase-returns.html` | Purchase returns, supplier debit notes |
| `supplier-invoices.html` | Supplier invoices, invoice events, VAT compliance |
| `supplier-payments.html` | Supplier payments, PDC, reversals, supplier statements |
| `sales-customers-quotations-lpos.html` | Customers, quotations, customer LPOs, product catalog / pricing |
| `accounts-receivable.html` | Sales invoices, payments received, credit control, credit notes, delivery & tax debit notes |
| `reports-analytics.html` | Reports, analytics dashboard, AR/AP aging, statement export |
| `auth-rbac.html` | Authentication, RBAC, workspaces, multi-tenant isolation |
| `communications.html` | WhatsApp and email communications |

All subgraphs are derived from real edges in `graph.json`; each includes the module's
own files plus their direct neighbours (one hop), capped for readability.

## Which file should I open?

- **Quick project overview:** `graph.html`
- **Project/file hierarchy:** `GRAPH_TREE.html`
- **Architecture / call flow:** `rezorpay_pro-callflow.html`
- **A specific subsystem:** `subgraphs/<name>.html`
- **Complete node-level detail:** `full-detail.html`
- **Raw machine-readable graph data:** `graph.json`

## How to regenerate

### One-shot helper (recommended)

```bash
# from the repository root
python scripts/graphify/regenerate.py
```

The helper:

1. checks the graph is current (`graph.json`'s `built_at_commit` vs. `git HEAD`);
   if stale it runs `graphify update .` to re-extract (cache-backed, no LLM);
2. runs `graphify cluster-only` to regenerate the overview with deterministic hub
   labels (**never** `--no-label`, so you get names like `ProductService` instead of
   `Community 12`);
3. regenerates `GRAPH_TREE.html`, `rezorpay_pro-callflow.html`;
4. regenerates every `subgraphs/*.html` and `full-detail.html`.

Extra flags: `--force-extract` (always re-extract), `--dry-run` (print predicted sizes
without writing).

### The underlying Graphify commands

The helper simply wraps the native CLI. The exact verified commands are:

```bash
graphify update .                                  # extract/update the graph (no LLM)
graphify cluster-only .                            # cluster + hub labels + graph.html + GRAPH_REPORT.md
graphify tree --graph graphify-out/graph.json \
              --output graphify-out/GRAPH_TREE.html
graphify export callflow-html . \
              --output graphify-out/rezorpay_pro-callflow.html
# subgraphs + full-detail are emitted by scripts/graphify/regenerate.py using
# the installed graphifyy package's to_html() with explicit output paths
# (the CLI's `export html` always writes graph.html, so a custom path is needed).
```

Note: `graphify cluster-only .` intentionally does **not** pass `--no-label`. Graphify's
deterministic, LLM-free hub labelling is used so community names are meaningful. No API
key is required and none should be added.

### Environment

The helper finds Graphify from, in order: `$GRAPHIFY_VENV` (a venv directory containing
`Scripts/graphify.exe` on Windows / `bin/graphify` on POSIX), `graphify` on `PATH`, or
`python -m graphify`. Install with `pip install graphifyy` if it is missing.

## Graph size

- **Nodes:** 5,357
- **Edges:** 19,367
- **Communities:** 197
- **Files indexed:** 437

The primary `graph.html` is deliberately the **aggregated** community view. Graphify
automates this: when a graph exceeds 5,000 nodes it collapses each community into one
node so the overview stays intelligible. Aggregating still happened inside `graph.html`
even though the labels are meaningful, so `graph.html` shows 197 community nodes (not
5,357 symbols). Use `full-detail.html` or a `subgraphs/*.html` file when you need the
individual functions/classes.

## Browser requirements

The interactive pages load their visualisation libraries from public CDNs, so they need
internet access the first time they are opened (the HTML itself is static and works from
`file://` — no server is required):

- `graph.html`, `full-detail.html`, `subgraphs/*.html` → `vis-network@9.1.6` (unpkg.com)
- `GRAPH_TREE.html` → `d3.v7` (d3js.org)
- `rezorpay_pro-callflow.html` → `mermaid@11` (cdn.jsdelivr.net)

Offline use is not guaranteed; these assets are **not** vendored in the repository.

## Authoritative cache

The current Graphify version (0.9.61) keeps its AST cache and manifest in
`graphify-out/cache/` and `graphify-out/manifest.json`. These are the authoritative
cache/output. An older `graphifyy/cache/` directory (from a previous Graphify
schema/version, `v0.9.53-s2`) used to be committed to the repo, but the installed
tool deliberately ignores caches from other versions, so it was removed — it had no
effect on this workflow. If a stray top-level `graphifyy/` or any other `v0.9.53-s2`
cache ever reappears, it can safely be deleted.

## Optional Obsidian export

Graphify can also export an Obsidian vault (one note per node plus a `graph.canvas`
community canvas). It is available via `graphify export obsidian` but is **not** included
in the repository permanently: it produces thousands of per-node notes (~5.5k files in
this repo), which would bloat the repository for little day-to-day benefit when the
HTML views above already cover navigation. Export it on demand if wanted:

```bash
graphify export obsidian --graph graphify-out/graph.json --dir /tmp/rezorpay-vault
```