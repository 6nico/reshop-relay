"""Metrics, guardrails, sensitivity runs, business value, and exports."""
from __future__ import annotations

import csv
import io
import json
import statistics


def summarize(sim):
    ev = sim.events
    items = sim.items
    close = sim.close
    placed = [i for i in items if i.status == "placed"]
    correct = [i for i in placed if not i.misplaced]
    arrived = [i for i in items if i.arrival <= close]
    remaining = [i for i in arrived if i.status != "placed"]

    reshop_min = sum(e["reshop_minutes"] for e in ev)
    reshop_m = sum(e["reshop_meters"] for e in ev)
    walk_m = sum(e["meters"] for e in ev)
    trips = sum(1 for e in ev if e["kind"] == "pickup" and not e.get("task"))
    piggy = sum(1 for e in ev if e["kind"] == "pickup" and e.get("task"))

    waits = [i.placed_at - i.arrival for i in placed]
    open_ages = [close - i.arrival for i in remaining]
    all_ages = waits + open_ages

    tasks = [t for t in sim.tasks if t.started is not None]
    late = [t for t in tasks if t.finished is not None and t.finished > t.deadline + 1e-9]
    delay = sum(t.finished - t.deadline for t in late)
    unstarted = [t for t in sim.tasks if t.started is None]

    # backlog over time (items waiting or in a cart, not yet placed)
    series, t = [], min(w.start for w in sim.workers)
    while t <= close + 1e-9:
        open_now = [i for i in items if i.arrival <= t and (i.placed_at is None or i.placed_at > t)]
        oldest = max((t - i.arrival for i in open_now), default=0.0)
        series.append({"t": round(t, 1), "open": len(open_now), "oldest_min": round(oldest, 1)})
        t += 15

    return {
        "strategy": sim.strategy,
        "seed": sim.seed,
        "items_arrived": len(arrived),
        "items_placed": len(placed),
        "items_correct": len(correct),
        "placement_errors": len(placed) - len(correct),
        "closing_backlog": len(remaining),
        "reshop_labor_min": round(reshop_min, 2),
        "reshop_walk_m": round(reshop_m, 1),
        "total_walk_m": round(walk_m, 1),
        "labor_min_per_correct_item": round(reshop_min / len(correct), 3) if correct else None,
        "dedicated_trips": trips,
        "collections_during_tasks": piggy,
        "avg_wait_min": round(statistics.mean(waits), 1) if waits else None,
        "max_age_min": round(max(all_ages), 1) if all_ages else 0.0,
        "tasks_total": len(sim.tasks),
        "tasks_late": len(late),
        "task_delay_min": round(delay, 2),
        "tasks_not_started": len(unstarted),
        "backlog_series": series,
        "events": ev,
        "decisions": sim.decisions,
    }


def reconcile(result):
    """Check that the dashboard totals match the event log (FR-6)."""
    ev = result["events"]
    placed_ids = [i for e in ev if e["kind"] == "place" for i in e["items"]]
    picked_ids = [i for e in ev if e["kind"] == "pickup" for i in e["items"]]
    checks = {
        "labor_matches_log": abs(sum(e["reshop_minutes"] for e in ev) - result["reshop_labor_min"]) < 0.05,
        "placed_matches_log": len(placed_ids) == result["items_placed"],
        "no_double_placement": len(placed_ids) == len(set(placed_ids)),
        "every_placed_item_was_picked": set(placed_ids) <= set(picked_ids),
        "items_conserved": result["items_placed"] + result["closing_backlog"] == result["items_arrived"],
    }
    return checks


def compare(results, target=0.20):
    """Compare strategies to the dedicated-trip baseline, with guardrails."""
    base = results["dedicated"]
    out = {}
    for name, r in results.items():
        b, x = base["labor_min_per_correct_item"], r["labor_min_per_correct_item"]
        reduction = (b - x) / b if b and x is not None else None
        err_rate = r["placement_errors"] / r["items_placed"] if r["items_placed"] else 0
        base_err = base["placement_errors"] / base["items_placed"] if base["items_placed"] else 0
        # Errors are decided per item up front, so small differences are just which items got returned.
        # Allow for that sampling noise (2 standard errors) before calling it worse.
        n = max(1, r["items_placed"])
        noise = 2 * (max(base_err, 0.01) * (1 - max(base_err, 0.01)) / n) ** 0.5
        guard = {
            "errors_not_higher": err_rate <= base_err + noise,
            "task_deadlines_kept": r["tasks_late"] <= base["tasks_late"] and r["tasks_not_started"] <= base["tasks_not_started"],
            "closing_backlog_not_higher": r["closing_backlog"] <= base["closing_backlog"],
            "oldest_item_not_older": r["max_age_min"] <= base["max_age_min"] + 1e-9,
        }
        out[name] = {
            "reduction_vs_dedicated": round(reduction, 4) if reduction is not None else None,
            "meets_target": bool(reduction is not None and reduction >= target and all(guard.values())) if name != "dedicated" else None,
            "guardrails": guard if name != "dedicated" else None,
        }
    return out


def business_value(results, cfg):
    A = cfg["assumptions"]
    val = lambda k: A[k]["value"] if isinstance(A[k], dict) else A[k]
    # Savings are per correctly returned item, times the items this strategy returned,
    # so a strategy cannot look good just by returning fewer items.
    b_per = results["dedicated"]["labor_min_per_correct_item"] or 0
    out = {}
    for name, r in results.items():
        x_per = r["labor_min_per_correct_item"] or 0
        saved = (b_per - x_per) * r["items_correct"]
        hours = saved / 60
        out[name] = {
            "labor_min_saved_per_day": round(saved, 1),
            "daily_hours_released": round(hours, 2),
            "annual_capacity_value": round(hours * val("operating_days") * val("hourly_labor_cost"), 0),
        }
    return out


def sensitivity(cfg, param, values, seeds):
    """Re-run all strategies across values of one assumption, with paired seeds."""
    import copy
    from .sim import run_all
    rows = []
    for v in values:
        c = copy.deepcopy(cfg)
        if isinstance(c["assumptions"][param], dict):
            c["assumptions"][param]["value"] = v
        else:
            c["assumptions"][param] = v
        per = {"dedicated": [], "opportunistic": [], "hybrid": []}
        red = {"opportunistic": [], "hybrid": []}
        back = {"dedicated": [], "opportunistic": [], "hybrid": []}
        for s in seeds:
            res = run_all(c, seed=s)
            for k in per:
                per[k].append(res[k]["labor_min_per_correct_item"] or 0)
                back[k].append(res[k]["closing_backlog"])
            for k in red:
                b, x = res["dedicated"]["labor_min_per_correct_item"], res[k]["labor_min_per_correct_item"]
                if b and x is not None:
                    red[k].append((b - x) / b)
        row = {"value": v}
        for k in per:
            row[k] = {"labor_per_item_mean": round(statistics.mean(per[k]), 3),
                      "closing_backlog_mean": round(statistics.mean(back[k]), 2)}
        for k in red:
            r = red[k]
            row[k].update({"reduction_mean": round(statistics.mean(r), 4) if r else None,
                           "reduction_min": round(min(r), 4) if r else None,
                           "reduction_max": round(max(r), 4) if r else None})
        rows.append(row)
    return rows


SUMMARY_FIELDS = ["strategy", "seed", "items_arrived", "items_placed", "items_correct", "placement_errors",
                  "closing_backlog", "reshop_labor_min", "reshop_walk_m", "total_walk_m",
                  "labor_min_per_correct_item", "dedicated_trips", "collections_during_tasks",
                  "avg_wait_min", "max_age_min", "tasks_total", "tasks_late", "task_delay_min", "tasks_not_started"]


def summary_csv(results):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=SUMMARY_FIELDS)
    w.writeheader()
    for r in results.values():
        w.writerow({k: r[k] for k in SUMMARY_FIELDS})
    return buf.getvalue()


def events_csv(results):
    buf = io.StringIO()
    fields = ["strategy", "worker", "kind", "t0", "t1", "minutes", "meters", "reshop_meters",
              "reshop_minutes", "task", "items", "note"]
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for name, r in results.items():
        for e in r["events"]:
            row = {k: e.get(k) for k in fields if k not in ("strategy", "items")}
            row["strategy"] = name
            row["items"] = " ".join(e["items"])
            w.writerow(row)
    return buf.getvalue()


def results_json(cfg, results):
    slim = {k: {kk: vv for kk, vv in v.items() if kk != "events"} for k, v in results.items()}
    return json.dumps({
        "scenario": cfg,
        "results": slim,
        "comparison": compare(results, cfg.get("target_reduction", 0.20)),
        "business_value": business_value(results, cfg),
        "reconciliation": {k: reconcile(v) for k, v in results.items()},
    }, indent=2)
