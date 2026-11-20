# Reshop Relay

**Retail Reshop Routing & Labor Efficiency** — a simulator that tests whether store team members can return
reshop (returned or abandoned items) to the shelf with less labor by collecting it during trips they already
make, instead of separate trips.

**Live demo:** https://6nico.github.io/reshop-relay/ (the Python engine runs in your browser with Pyodide)

![strategies](https://img.shields.io/badge/strategies-dedicated%20·%20during%20trips%20·%20hybrid-8fb0ff) ![tests](https://img.shields.io/badge/tests-17%20passing-34d399)

## What it does

- Builds a fictional store as a walkable graph (shortest paths with Dijkstra; blocked aisles respected).
- Generates reshop arriving at Guest Services over a shift, sorted by department (seeded, reproducible).
- Simulates team members with shifts, carts, and existing work that has deadlines (freight, fulfillment, breaks, backup cashier).
- Compares three strategies with **identical inputs**:
  - **Dedicated** — separate trips to Guest Services when enough reshop waits or the oldest item gets old.
  - **During existing trips** — collect a batch only when it fits the cart, the detour is short, and no task deadline is put at risk.
  - **Hybrid** — collect during trips, plus a dedicated trip when the backlog or age passes a threshold.
- Orders drop-off stops with **nearest-neighbor + 2-opt**.
- Explains every pickup decision ("detour too long", "would delay later tasks", …).
- Reports labor minutes per correctly returned item **next to** reshop left at close, oldest item age, task delays, and errors, so a method can't look good by doing less.
- Runs sensitivity sweeps over paired random seeds, and estimates labor capacity released.
- Exports results JSON, a summary CSV, and the full event log CSV. Totals reconcile with the event log.

## Early findings (fictional store, default assumptions, average of 10 paired seeds)

| Scenario | During trips only: labor per item | Left at close (dedicated → during trips) | Hybrid: labor per item | Left at close (dedicated → hybrid) |
|---|---|---|---|---|
| Low volume | 38% less | 14 → 45 | 14% less | 14 → 16 |
| Medium volume | 31% less | 46 → 127 | 13% less | 46 → 53 |
| High volume | 28% less | 118 → 250 | 12% less | 118 → 122 |

Collecting only during existing trips is efficient but can't keep up by itself. Hybrid gives a real but
smaller gain with a slightly bigger backlog, and **does not reach the 20% target** under these assumptions.
That matches the PRD's warning that some backlog is a staffing problem, not a routing problem. These are
simulated results, not store results.

## Run it locally

```sh
python -m reshop_relay run scenarios/medium.json --out results/
python -m reshop_relay sweep scenarios/medium.json arrival_volume_multiplier 0.5,1,1.5 --seeds 1,2,3,4,5
python -m pytest tests
```

Python 3.10+ and no dependencies (pytest for tests). To view the dashboard locally:
`python -m http.server` and open http://localhost:8000.

## Project layout

```
reshop_relay/   store.py (graph, routing, 2-opt) · sim.py (shift simulation, strategies)
                metrics.py (results, guardrails, sensitivity, exports) · web.py (browser bridge)
scenarios/      low / medium / high volume (built by tools/make_scenarios.py)
tests/          item conservation, routes, capacity, shift limits, reproducibility
index.html, app.js, app.css   dashboard
docs/RESEARCH.md              forum research behind the defaults
```

## Honest limits

- Fictional store, staff, and tasks. No real retailer data.
- Department-level drop-offs only; the model does not know exact shelf spots.
- Volumes and handling times are assumptions until measured (PRD Stage 3 mock test).
- Labor capacity released is time freed for other work, not payroll savings.

Built by [Nicolas Olmos](https://6nico.github.io).
