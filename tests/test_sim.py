"""Stage 1 checks from the PRD: item conservation, valid routes, capacity, shift limits, reproducibility."""
import copy
import json
import pathlib

import pytest

from reshop_relay import Store, UnreachableError, Sim, run_all, reconcile, compare
from reshop_relay.sim import STRATEGIES, generate_arrivals

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(name="medium"):
    return json.loads((ROOT / "scenarios" / f"{name}.json").read_text())


@pytest.fixture(scope="module")
def results():
    return run_all(load())


def test_blocking_a_connection_changes_routes():
    cfg = load()
    s1 = Store.from_dict(cfg["store"])
    before = s1.dist("GS", "STYLE")
    cfg["store"]["blocked"] = [["RT1", "STYLE"]]
    s2 = Store.from_dict(cfg["store"])
    assert s2.dist("GS", "STYLE") > before
    assert "RT1" not in s2.path("GS", "STYLE")[1:-1] or s2.path("GS", "STYLE")[-2] != "RT1"


def test_unreachable_destination_is_reported():
    cfg = load()
    cfg["store"]["blocked"] = [["RT4", "MARKET"], ["MARKET", "RT5"]]
    with pytest.raises(UnreachableError, match="Market"):
        Sim(cfg, "dedicated")


def test_two_opt_never_worse_than_given_order():
    s = Store.from_dict(load()["store"])
    stops = ["MARKET", "STYLE", "TOYS", "BEAUTY", "ELEC"]
    best = s.order_stops("GS", stops)
    assert sorted(best) == sorted(stops)
    assert s.route_length(["GS"] + best) <= s.route_length(["GS"] + stops) + 1e-9


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_items_conserved_and_never_early(results, strategy):
    r = results[strategy]
    assert all(reconcile(r).values()), reconcile(r)
    sim_items = {i.id: i for i in generate_arrivals(load(), load()["seed"])}
    for e in r["events"]:
        if e["kind"] == "pickup":
            for iid in e["items"]:
                assert sim_items[iid].arrival <= e["t0"] + 1e-6, "collected before it arrived"


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_cart_capacity_and_shift_limits(strategy):
    cfg = load()
    sim = Sim(cfg, strategy)
    r = sim.run()
    cap = {w.id: w.cart_capacity for w in sim.workers}
    end = {w.id: w.end for w in sim.workers}
    for e in r["events"]:
        if e["kind"] == "pickup":
            assert len(e["items"]) <= cap[e["worker"]]
        assert e["t1"] <= end[e["worker"]] + 1e-6, f"work after shift end: {e}"


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_no_overlapping_work_per_worker(results, strategy):
    by = {}
    for e in results[strategy]["events"]:
        by.setdefault(e["worker"], []).append(e)
    for evs in by.values():
        evs.sort(key=lambda e: (e["t0"], e["t1"]))
        for a, b in zip(evs, evs[1:]):
            assert b["t0"] >= a["t1"] - 1e-6, (a, b)


def test_same_seed_same_results():
    a, b = run_all(load(), seed=11), run_all(load(), seed=11)
    for s in STRATEGIES:
        assert {k: v for k, v in a[s].items()} == {k: v for k, v in b[s].items()}


def test_strategies_get_identical_inputs(results):
    arrived = {s: results[s]["items_arrived"] for s in STRATEGIES}
    tasks = {s: results[s]["tasks_total"] for s in STRATEGIES}
    assert len(set(arrived.values())) == 1 and len(set(tasks.values())) == 1


def test_dedicated_never_collects_during_tasks(results):
    assert results["dedicated"]["collections_during_tasks"] == 0
    assert results["opportunistic"]["dedicated_trips"] == 0


def test_every_skip_has_a_reason(results):
    for d in results["opportunistic"]["decisions"]:
        assert d["reason"]
        if d["decision"] == "skip":
            assert d["items"] == 0


def test_comparison_reports_backlog_not_just_efficiency(results):
    c = compare(results)
    # opportunistic alone looks efficient but leaves more behind, so it must not "meet target"
    assert results["opportunistic"]["closing_backlog"] > results["dedicated"]["closing_backlog"]
    assert c["opportunistic"]["meets_target"] is False
