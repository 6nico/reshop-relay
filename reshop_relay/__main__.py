"""Command line: python -m reshop_relay run scenarios/medium.json --out results/"""
import argparse
import json
import pathlib

from .sim import run_all
from .metrics import compare, summary_csv, events_csv, results_json, reconcile, sensitivity


def main(argv=None):
    p = argparse.ArgumentParser(prog="reshop_relay", description="Compare reshop collection strategies.")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="Run all three strategies on a scenario")
    r.add_argument("scenario")
    r.add_argument("--seed", type=int)
    r.add_argument("--out", default="results")
    s = sub.add_parser("sweep", help="Sensitivity: vary one assumption across paired seeds")
    s.add_argument("scenario")
    s.add_argument("param")
    s.add_argument("values", help="comma-separated values, e.g. 0.5,1,1.5")
    s.add_argument("--seeds", default="1,2,3,4,5")
    a = p.parse_args(argv)

    cfg = json.loads(pathlib.Path(a.scenario).read_text())
    if a.cmd == "run":
        res = run_all(cfg, seed=a.seed)
        out = pathlib.Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "results.json").write_text(results_json(cfg, res))
        (out / "summary.csv").write_text(summary_csv(res))
        (out / "events.csv").write_text(events_csv(res))
        cmp_ = compare(res, cfg.get("target_reduction", 0.20))
        print(f"{cfg['name']}  (seed {res['dedicated']['seed']})")
        print(f"{'strategy':<15}{'placed':>8}{'left':>6}{'labor min':>11}{'min/item':>10}{'vs base':>9}")
        for k, v in res.items():
            red = cmp_[k]["reduction_vs_dedicated"]
            print(f"{k:<15}{v['items_placed']:>8}{v['closing_backlog']:>6}{v['reshop_labor_min']:>11.1f}"
                  f"{v['labor_min_per_correct_item'] or 0:>10.3f}{(red or 0) * 100:>8.1f}%")
        bad = [k for k, v in res.items() if not all(reconcile(v).values())]
        print("Totals reconcile with event log:", "yes" if not bad else f"NO ({bad})")
        print(f"Wrote {out}/results.json, summary.csv, events.csv")
    else:
        vals = [float(x) for x in a.values.split(",")]
        seeds = [int(x) for x in a.seeds.split(",")]
        rows = sensitivity(cfg, a.param, vals, seeds)
        print(f"{a.param:<12}{'opp reduction':>16}{'hybrid reduction':>18}{'hybrid left':>13}{'base left':>11}")
        for row in rows:
            o, h = row["opportunistic"], row["hybrid"]
            print(f"{row['value']:<12}{o['reduction_mean'] * 100:>15.1f}%{h['reduction_mean'] * 100:>17.1f}%"
                  f"{h['closing_backlog_mean']:>13}{row['dedicated']['closing_backlog_mean']:>11}")


if __name__ == "__main__":
    main()
