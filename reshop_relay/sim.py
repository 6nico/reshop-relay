"""Shift simulation: reshop arrivals, workers, tasks, and three collection strategies.

Times are in minutes from the start of the simulated day. Every strategy gets
an identical copy of the same arrivals, staffing, tasks and starting state.
"""
from __future__ import annotations

import copy
import hashlib
import math
import random
from dataclasses import dataclass, field

from .store import Store, UnreachableError

STRATEGIES = ("dedicated", "opportunistic", "hybrid")
STRATEGY_LABELS = {
    "dedicated": "Dedicated trips",
    "opportunistic": "During existing trips",
    "hybrid": "Hybrid",
}


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
@dataclass
class Item:
    id: str
    dept: str
    arrival: float
    place_sec: float
    misplaced: bool = False          # decided up front so every strategy faces the same errors
    status: str = "waiting"          # waiting -> collected -> placed
    collected_at: float | None = None
    placed_at: float | None = None
    by: str | None = None


@dataclass
class Task:
    id: str
    worker: str
    label: str
    release: float
    deadline: float
    start: str        # where the task's freight is picked up (e.g. backroom)
    dest: str         # where the work happens
    work_min: float
    cart_load: int    # cart slots the task itself uses
    skipped: bool = False      # could not fit in the shift
    pickup: str = "before"   # when this trip passes Guest Services: before the work or after it
    return_home: bool = False  # after the work the worker walks back to their area
    started: float | None = None
    finished: float | None = None


@dataclass
class Worker:
    id: str
    name: str
    start: float
    end: float
    home: str
    departments: list
    cart_capacity: int
    t: float = 0.0
    loc: str = ""


def _assume(cfg, key):
    a = cfg["assumptions"][key]
    return a["value"] if isinstance(a, dict) else a


def _item_hash(seed, item_id):
    h = hashlib.sha256(f"{seed}:{item_id}".encode()).hexdigest()
    return int(h[:12], 16) / float(16 ** 12)


# --------------------------------------------------------------------------
# Building inputs from a scenario
# --------------------------------------------------------------------------
def generate_arrivals(cfg, seed):
    """Reshop items arriving at Guest Services, already sorted by department."""
    rng = random.Random(seed)
    arr = cfg["arrivals"]
    volume = float(_assume(cfg, "arrival_volume_multiplier"))
    profile = arr["hourly_rate"]                 # items per hour, one entry per hour of the day
    weights = arr["dept_weights"]
    depts, w = list(weights), list(weights.values())
    place_sec = float(_assume(cfg, "place_sec"))
    err = float(_assume(cfg, "placement_error_rate"))
    start = float(arr.get("start", 0))
    items, n = [], 0
    # Poisson arrivals, hour by hour, so the rate can change across the day.
    for hour, per_hour in enumerate(profile):
        rate = per_hour * volume / 60.0               # items per minute
        t, end = start + 60 * hour, start + 60 * (hour + 1)
        while rate > 0:
            t += rng.expovariate(rate)
            if t >= end:
                break
            n += 1
            iid = f"R{n:04d}"
            items.append(Item(
                id=iid,
                dept=rng.choices(depts, w)[0],
                arrival=round(t, 3),
                place_sec=round(place_sec * rng.uniform(0.7, 1.3), 2),
                misplaced=_item_hash(seed, iid) < err,
            ))
    return items


def build_tasks(cfg):
    """Existing work (stocking, fulfillment, etc.) each worker must still finish on time."""
    tasks = []
    for w in cfg["workers"]:
        for k, spec in enumerate(w.get("tasks", [])):
            t, i = w["start"] + spec.get("offset", 0), 0
            while t + spec["work"] <= w["end"]:
                i += 1
                tasks.append(Task(
                    id=f"{w['id']}-{k}-{i}", worker=w["id"], label=spec["label"],
                    release=float(t), deadline=float(t + spec["window"]),
                    start=spec.get("start", spec["dest"]), dest=spec["dest"],
                    work_min=float(spec["work"]), cart_load=int(spec.get("cart_load", 0)),
                    pickup=spec.get("pickup", "before"), return_home=bool(spec.get("return_home", False)),
                ))
                t += spec["every"]
    tasks.sort(key=lambda x: (x.release, x.id))
    return tasks


def build_workers(cfg):
    out = []
    for w in cfg["workers"]:
        out.append(Worker(id=w["id"], name=w.get("name", w["id"]), start=float(w["start"]),
                          end=float(w["end"]), home=w["home"], departments=list(w["departments"]),
                          cart_capacity=int(w.get("cart_capacity", _assume(cfg, "cart_capacity"))),
                          t=float(w["start"]), loc=w["home"]))
    return out


def validate(cfg, store, workers, tasks):
    problems = []
    for dept in store.check_reachable():
        problems.append(f"Department '{dept}' cannot be reached from Guest Services.")
    for w in workers:
        for d in w.departments:
            if d not in store.departments:
                problems.append(f"{w.name} is assigned unknown department '{d}'.")
        if w.home not in store.nodes:
            problems.append(f"{w.name} starts at unknown location '{w.home}'.")
    for t in tasks:
        for n in (t.start, t.dest):
            if n not in store.nodes:
                problems.append(f"Task {t.id} uses unknown location '{n}'.")
    return problems


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------
class Sim:
    def __init__(self, cfg, strategy, seed=None, items=None):
        if strategy not in STRATEGIES:
            raise ValueError(f"Unknown strategy {strategy}")
        self.cfg = cfg
        self.strategy = strategy
        self.seed = cfg.get("seed", 1) if seed is None else seed
        self.store = Store.from_dict(cfg["store"])
        self.workers = build_workers(cfg)
        self.tasks = build_tasks(cfg)
        problems = validate(cfg, self.store, self.workers, self.tasks)
        if problems:
            raise UnreachableError(" ".join(problems))
        self.items = copy.deepcopy(items) if items is not None else generate_arrivals(cfg, self.seed)
        self.A = {k: _assume(cfg, k) for k in cfg["assumptions"]}
        self.speed = float(self.A["walk_speed_m_per_min"])
        self.events = []
        self._last = {}
        self.decisions = []
        self.close = max(w.end for w in self.workers)

    # ---- helpers ---------------------------------------------------------
    def waiting(self, t, depts=None):
        return [i for i in self.items if i.status == "waiting" and i.arrival <= t + 1e-9
                and (depts is None or i.dept in depts)]

    def walk_min(self, meters):
        return meters / self.speed

    def log(self, w, kind, t0, t1, meters=0.0, reshop_meters=0.0, reshop_min=0.0, items=(), task=None,
            path=None, note=""):
        last = self._last.get(w.id)
        if kind == "idle" and last is not None and last["kind"] == "idle" and abs(last["t1"] - round(t0, 4)) < 1e-6:
            last["t1"] = round(t1, 4)
            last["minutes"] = round(last["t1"] - last["t0"], 4)
            return
        self.events.append({
            "worker": w.id, "kind": kind, "t0": round(t0, 4), "t1": round(t1, 4),
            "minutes": round(t1 - t0, 4), "meters": round(meters, 3),
            "reshop_meters": round(reshop_meters, 3), "reshop_minutes": round(reshop_min, 4),
            "items": list(items), "task": task, "path": path or [], "note": note,
        })
        self._last[w.id] = self.events[-1]

    def next_task(self, w, t, skip=None):
        for k in self.tasks:
            if k.worker == w.id and k.started is None and not k.skipped and k is not skip:
                return k
        return None

    def handling_min(self, batch, extra_coord=False):
        A = self.A
        m = A["pickup_setup_sec"] / 60 + len(batch) * A["scan_sec"] / 60
        if extra_coord:
            m += A["coordination_sec"] / 60
        return m

    def place_min(self, batch):
        return sum(i.place_sec for i in batch) / 60

    def correction_min(self, batch):
        return sum(self.A["correction_min"] for i in batch if i.misplaced)

    # ---- batch selection (FR-5) -------------------------------------------
    def select_batch(self, w, t, capacity, start_loc, base_stops, mode):
        """Pick reshop for this trip.

        mode 'piggyback': route is start_loc -> GS -> base_stops..., drops after the task.
        mode 'dedicated': route is start_loc -> GS -> drops.
        Returns (batch, drop_order, extra_meters, reason).
        """
        A = self.A
        gs = self.store.guest_services
        if capacity <= 0:
            return [], [], 0.0, "cart has no free space"
        pool = self.waiting(t, w.departments)
        if not pool:
            return [], [], 0.0, "no waiting reshop for this worker's departments"
        pool.sort(key=lambda i: (i.arrival, i.id))       # oldest first
        by_dept = {}
        for i in pool:
            by_dept.setdefault(i.dept, []).append(i)

        def drops_for(batch, from_node):
            stops = [self.store.departments[i.dept] for i in batch]
            return self.store.order_stops(from_node, stops)

        if mode == "piggyback":
            base = self.store.route_length([start_loc] + base_stops)
            with_gs = self.store.route_length([start_loc, gs] + base_stops)
            drop_from = base_stops[-1]
        else:
            base = 0.0
            with_gs = self.store.dist(start_loc, gs)
            drop_from = gs

        age_w = float(A["age_priority_weight"])

        def dept_priority(d):
            items = by_dept[d]
            age = t - items[0].arrival
            dist = self.store.dist(drop_from, self.store.departments[d])
            return -(len(items) + age_w * age) + dist / 50.0

        batch, order = [], []
        for d in sorted(by_dept, key=lambda d: (dept_priority(d), d)):
            room = capacity - len(batch)
            if room <= 0:
                break
            trial = batch + by_dept[d][:room]
            o = drops_for(trial, drop_from)
            extra = with_gs - base + self.store.route_length([drop_from] + o)
            if mode == "piggyback" and extra / len(trial) > A["max_detour_m_per_item"]:
                continue
            batch, order = trial, o
        if not batch:
            per = (with_gs - base) / max(1, len(pool))
            return [], [], 0.0, f"detour too long for the reshop waiting (limit {A['max_detour_m_per_item']} m per item)"
        extra = with_gs - base + self.store.route_length([drop_from] + order)
        return batch, order, extra, "selected"

    # ---- actions -----------------------------------------------------------
    def do_task(self, w, task, t):
        """Run an existing task; optionally collect reshop on the same trip (opportunistic / hybrid).

        pickup="before": the trip to the task can swing by Guest Services first (e.g. coming from the front).
        pickup="after":  after the work (e.g. break, backup cashier) the walk back can pass Guest Services.
        """
        A = self.A
        gs = self.store.guest_services
        t = max(t, task.release)
        home = w.home
        batch, order, extra, reason = [], [], 0.0, "strategy does not collect during tasks"
        if self.strategy in ("opportunistic", "hybrid"):
            if task.pickup == "after":
                capacity = w.cart_capacity
                # baseline walk after the work: dest -> home (if returning) ; with reshop: dest -> GS -> drops
                batch, order, extra, reason = self.select_batch(w, t, capacity, task.dest, [], "dedicated")
                if batch:
                    base_back = self.store.dist(task.dest, home) if task.return_home else 0.0
                    route = self.store.route_length([task.dest, gs] + order)
                    extra = route - base_back
                    if extra / len(batch) > A["max_detour_m_per_item"]:
                        batch, order, reason = [], [], f"detour too long for the reshop waiting (limit {A['max_detour_m_per_item']} m per item)"
            else:
                capacity = w.cart_capacity - task.cart_load
                batch, order, extra, reason = self.select_batch(w, t, capacity, w.loc, [task.start, task.dest], "piggyback")
            if batch:
                pre = self.store.route_length([w.loc, gs, task.start, task.dest] if task.pickup == "before" else [w.loc, task.start, task.dest])
                finish = t + self.walk_min(pre) + (self.handling_min(batch, True) if task.pickup == "before" else 0) + task.work_min
                tail = self.store.route_length(([task.dest] + order) if task.pickup == "before" else ([task.dest, gs] + order))
                drop_end = finish + self.walk_min(tail) + self.place_min(batch) + (self.handling_min(batch, True) if task.pickup == "after" else 0)
                # what the rest of the shift looks like without reshop on this trip
                plain_fin = t + self.walk_min(self.store.route_length([w.loc, task.start, task.dest])) + task.work_min
                plain_loc = task.dest
                if task.return_home:
                    plain_fin += self.walk_min(self.store.dist(task.dest, home))
                    plain_loc = home
                end_loc = order[-1] if order else (gs if task.pickup == "after" else task.dest)
                if finish > max(task.deadline - A["deadline_buffer_min"], plain_fin) + 1e-9:
                    batch, order, extra, reason = [], [], 0.0, "would risk the task deadline"
                elif self.est_lateness(w, drop_end, end_loc, skip=task) > self.est_lateness(w, plain_fin, plain_loc, skip=task) + 1e-6:
                    batch, order, extra, reason = [], [], 0.0, "would delay later tasks"
                elif drop_end > w.end:
                    batch, order, extra, reason = [], [], 0.0, "not enough shift time left to place items"
            self.decisions.append({
                "t": round(t, 2), "worker": w.name, "task": task.label, "items": len(batch),
                "departments": sorted({i.dept for i in batch}), "extra_m": round(extra, 1) if batch else None,
                "decision": "collect" if batch else "skip", "reason": reason,
            })
        task.started = t
        if batch and task.pickup == "before":
            leg = [w.loc, gs, task.start, task.dest]
            meters = self.store.route_length(leg)
            reshop_m = meters - self.store.route_length([w.loc, task.start, task.dest])
            t1 = t + self.walk_min(meters)
            self.log(w, "walk", t, t1, meters, reshop_m, self.walk_min(reshop_m), task=task.id,
                     path=self.store.full_path(leg), note="to task via Guest Services")
            hm = self.handling_min(batch, True)
            self.log(w, "pickup", t1, t1 + hm, reshop_min=hm, items=[i.id for i in batch], task=task.id,
                     note="scan + coordination at Guest Services")
            for i in batch:
                i.status, i.collected_at, i.by = "collected", t1, w.id
            t = t1 + hm
        else:
            leg = [w.loc, task.start, task.dest]
            meters = self.store.route_length(leg)
            t1 = t + self.walk_min(meters)
            self.log(w, "walk", t, t1, meters, task=task.id, path=self.store.full_path(leg), note="to task")
            t = t1
        self.log(w, "task", t, t + task.work_min, task=task.id, note=task.label)
        t += task.work_min
        task.finished = t
        w.loc = task.dest
        if batch and task.pickup == "after":
            base_back = self.store.dist(task.dest, home) if task.return_home else 0.0
            m = self.store.dist(task.dest, gs)
            # the part of the walk that replaces the normal walk back is task time, the rest is reshop
            self.log(w, "walk", t, t + self.walk_min(m), m, max(0.0, m - base_back), self.walk_min(max(0.0, m - base_back)),
                     task=task.id, path=self.store.path(task.dest, gs), note="back via Guest Services")
            t += self.walk_min(m)
            hm = self.handling_min(batch, True)
            self.log(w, "pickup", t, t + hm, reshop_min=hm, items=[i.id for i in batch], task=task.id,
                     note="pickup on the way back")
            for i in batch:
                i.status, i.collected_at, i.by = "collected", t, w.id
            t += hm
            w.loc = gs
            credit = max(0.0, base_back - m)   # walk-back meters already counted above
            t = self.drop_off(w, batch, order, t, gs, credit_m=credit)
        elif batch:
            t = self.drop_off(w, batch, order, t, task.dest)
        elif task.return_home and w.loc != home and t + self.walk_min(self.store.dist(w.loc, home)) <= w.end:
            m = self.store.dist(w.loc, home)
            self.log(w, "walk", t, t + self.walk_min(m), m, task=task.id, path=self.store.path(w.loc, home), note="back to area")
            t += self.walk_min(m)
            w.loc = home
        w.t = t

    def drop_off(self, w, batch, order, t, start, credit_m=0.0):
        """Walk the ordered stops and place items. credit_m: meters of this walk that the worker
        would have walked anyway (e.g. heading back to their area), so they are not counted as reshop."""
        loc = start
        stops = list(order)
        if any(self.store.departments[i.dept] == start for i in batch) and start not in stops:
            stops = [start] + stops          # items for the spot we are already standing in
        for stop in stops:
            here = [i for i in batch if self.store.departments[i.dept] == stop]
            m = self.store.dist(loc, stop)
            rm = max(0.0, m - credit_m)
            credit_m = max(0.0, credit_m - m)
            self.log(w, "walk", t, t + self.walk_min(m), m, rm, self.walk_min(rm),
                     path=self.store.path(loc, stop), note="reshop drop-off")
            t += self.walk_min(m)
            pm = self.place_min(here) + self.correction_min(here)
            self.log(w, "place", t, t + pm, reshop_min=pm, items=[i.id for i in here],
                     note=f"place {len(here)} item(s) in {stop}")
            t += pm
            for i in here:
                i.status, i.placed_at = "placed", t
            loc = stop
        w.loc = loc
        return t

    def dedicated_trip(self, w, t, limit_t):
        """Separate reshop trip: go to Guest Services, collect, return items."""
        gs = self.store.guest_services
        batch, order, extra, reason = self.select_batch(w, t, w.cart_capacity, w.loc, [], "dedicated")
        # shrink the batch until it fits the time available
        while batch:
            dur = (self.walk_min(self.store.route_length([w.loc, gs] + order)) + self.handling_min(batch)
                   + self.place_min(batch) + self.correction_min(batch))
            end_loc = order[-1] if order else gs
            if t + dur <= limit_t + 1e-9 and self.est_lateness(w, t + dur, end_loc) <= self.est_lateness(w, t, w.loc) + 1e-6:
                break
            batch = batch[:-1]
            order = self.store.order_stops(gs, [self.store.departments[i.dept] for i in batch])
        if not batch:
            return False
        m = self.store.dist(w.loc, gs)
        self.log(w, "walk", t, t + self.walk_min(m), m, m, self.walk_min(m),
                 path=self.store.path(w.loc, gs), note="dedicated trip to Guest Services")
        t += self.walk_min(m)
        hm = self.handling_min(batch)
        self.log(w, "pickup", t, t + hm, reshop_min=hm, items=[i.id for i in batch], note="dedicated pickup")
        for i in batch:
            i.status, i.collected_at, i.by = "collected", t, w.id
        t += hm
        w.loc = gs
        w.t = self.drop_off(w, batch, order, t, gs)
        self.decisions.append({
            "t": round(t, 2), "worker": w.name, "task": "Dedicated reshop trip", "items": len(batch),
            "departments": sorted({i.dept for i in batch}), "extra_m": None,
            "decision": "dedicated trip", "reason": "backlog or age trigger reached",
        })
        return True

    def trigger(self, w, t):
        A = self.A
        pool = self.waiting(t, w.departments)
        if not pool:
            return False
        oldest = t - min(i.arrival for i in pool)
        if self.strategy == "dedicated":
            return len(pool) >= A["dedicated_min_batch"] or oldest >= A["dedicated_age_trigger_min"]
        if self.strategy == "hybrid":
            return len(pool) >= A["hybrid_backlog_trigger"] or oldest >= A["hybrid_age_trigger_min"]
        return False

    def est_lateness(self, w, t, loc, skip=None):
        """Estimated total lateness (min) of this worker's remaining tasks if they are free at (t, loc)."""
        late = 0.0
        for k in self.tasks:
            if k.worker != w.id or k.started is not None or k.skipped or k is skip:
                continue
            start = max(t, k.release)
            fin = start + self.walk_min(self.store.route_length([loc, k.start, k.dest])) + k.work_min
            late += max(0.0, fin - k.deadline) + 10 * max(0.0, fin - w.end)
            t, loc = fin, k.dest
            if k.return_home:
                t += self.walk_min(self.store.dist(loc, w.home))
                loc = w.home
        return late

    # ---- main loop ---------------------------------------------------------
    def run(self):
        step = 2.0
        guard = 0
        active = list(self.workers)
        while active:
            guard += 1
            if guard > 200000:
                raise RuntimeError("Simulation did not converge")
            w = min(active, key=lambda x: (x.t, x.id))
            t = w.t
            if t >= w.end - 1e-9:
                active.remove(w)
                continue
            task = self.next_task(w, t)
            if task and task.release <= t + 1e-9:
                est = t + self.walk_min(self.store.route_length([w.loc, task.start, task.dest])) + task.work_min
                if est > w.end + 1e-9:
                    task.skipped = True          # does not fit in the shift; reported as not started
                    continue
                self.do_task(w, task, t)
                continue
            next_rel = task.release if task else w.end
            limit = w.end
            if self.strategy != "opportunistic" and self.trigger(w, t) and limit > t:
                if self.dedicated_trip(w, t, limit):
                    continue
            # idle until something changes
            nxt = min(next_rel, t + step, w.end)
            if nxt <= t:
                nxt = t + step
            self.log(w, "idle", t, nxt, note="available")
            w.t = nxt
        return self.results()

    # ---- results -------------------------------------------------------------
    def results(self):
        from .metrics import summarize
        return summarize(self)


def run_all(cfg, seed=None):
    """Run all three strategies with identical inputs (paired comparison)."""
    seed = cfg.get("seed", 1) if seed is None else seed
    items = generate_arrivals(cfg, seed)
    out = {}
    for s in STRATEGIES:
        out[s] = Sim(cfg, s, seed=seed, items=items).run()
    return out
