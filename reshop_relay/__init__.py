"""Reshop Relay: simulate and compare ways to return reshop to the sales floor."""
from .store import Store, UnreachableError
from .sim import Sim, run_all, STRATEGIES, STRATEGY_LABELS
from .metrics import compare, reconcile, business_value, sensitivity, summary_csv, events_csv, results_json

__version__ = "0.1.0"
