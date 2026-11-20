"""Small JSON bridge used by the browser dashboard (runs under Pyodide)."""
import json

from .sim import run_all
from .metrics import compare, business_value, reconcile, sensitivity, summary_csv, events_csv, results_json


def run(cfg_json, seed=None):
    cfg = json.loads(cfg_json)
    res = run_all(cfg, seed=seed)
    return json.dumps({
        "results": res,
        "comparison": compare(res, cfg.get("target_reduction", 0.20)),
        "business": business_value(res, cfg),
        "reconcile": {k: reconcile(v) for k, v in res.items()},
        "exports": {
            "summary_csv": summary_csv(res),
            "events_csv": events_csv(res),
            "results_json": results_json(cfg, res),
        },
    })


def sweep(cfg_json, param, values_json, seeds_json):
    cfg = json.loads(cfg_json)
    return json.dumps(sensitivity(cfg, param, json.loads(values_json), json.loads(seeds_json)))
