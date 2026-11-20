"""Builds the sample scenario files in scenarios/. Fictional store; see docs/RESEARCH.md for sources."""
import copy, json, math, pathlib

N = {  # node: (x, y, label)   meters, y=0 is the front of the store
    "GS": (6, 4, "Guest Services"), "CL": (40, 4, "Checklanes"), "BRK": (22, 0, "Break room"),
    "RT1": (6, 14, "Front aisle W"), "RT2": (40, 14, "Front aisle mid"), "RT3": (75, 14, "Front aisle E"), "RT4": (104, 14, "Front aisle far E"),
    "RT5": (104, 62, "Back aisle far E"), "RT6": (75, 62, "Back aisle E"), "DOOR": (57, 62, "Backroom door"), "RT7": (40, 62, "Back aisle mid"), "RT8": (6, 62, "Back aisle W"),
    "C1": (40, 38, "Center aisle W"), "C2": (75, 38, "Center aisle E"), "BR": (57, 72, "Backroom"),
    "STYLE": (20, 38, "Style (apparel)"), "BEAUTY": (40, 26, "Beauty"), "HOME": (57, 38, "Home"),
    "KITCHEN": (57, 52, "Kitchen"), "SEASONAL": (75, 26, "Seasonal"), "ELEC": (90, 26, "Electronics"),
    "TOYS": (90, 50, "Toys"), "MARKET": (112, 38, "Market (grocery)"),
}
E = [("GS", "RT1"), ("GS", "BRK"), ("BRK", "CL"), ("CL", "RT2"), ("RT1", "RT2"), ("RT2", "RT3"), ("RT3", "RT4"), ("RT4", "RT5"),
     ("RT5", "RT6"), ("RT6", "DOOR"), ("DOOR", "RT7"), ("RT7", "RT8"), ("RT8", "RT1"), ("DOOR", "BR"),
     ("RT1", "STYLE"), ("RT8", "STYLE"), ("STYLE", "C1"), ("RT2", "BEAUTY"), ("BEAUTY", "C1"), ("C1", "RT7"),
     ("C1", "HOME"), ("HOME", "C2"), ("HOME", "KITCHEN"), ("KITCHEN", "DOOR"), ("RT3", "SEASONAL"), ("SEASONAL", "C2"),
     ("C2", "RT6"), ("RT3", "ELEC"), ("ELEC", "C2"), ("ELEC", "RT4"), ("C2", "TOYS"), ("TOYS", "RT5"), ("TOYS", "RT6"),
     ("RT4", "MARKET"), ("MARKET", "RT5")]


def d(a, b):
    (x1, y1, _), (x2, y2, _) = N[a], N[b]
    return round(math.hypot(x1 - x2, y1 - y2), 1)


store = {
    "nodes": {k: {"x": v[0], "y": v[1], "label": v[2]} for k, v in N.items()},
    "edges": [[a, b, d(a, b)] for a, b in E],
    "departments": {"Style": "STYLE", "Beauty": "BEAUTY", "Home": "HOME", "Kitchen": "KITCHEN",
                    "Seasonal": "SEASONAL", "Electronics": "ELEC", "Toys": "TOYS", "Market": "MARKET"},
    "guest_services": "GS",
    "blocked": [],
}

A = lambda v, src, label, note="": {"value": v, "source": src, "label": label, "note": note}
assumptions = {
    "arrival_volume_multiplier": A(1.0, "assumption", "Reshop volume multiplier"),
    "walk_speed_m_per_min": A(60, "assumption", "Walking speed with a cart (m/min)", "About 1 m/s; slower than normal walking because of the cart."),
    "cart_capacity": A(10, "forum", "Reshop items per cart", "One store reported a rule of no more than 10 reshop items per cart."),
    "pickup_setup_sec": A(45, "assumption", "Pickup setup at Guest Services (sec per pickup)"),
    "scan_sec": A(3, "assumption", "Scan / check per item at pickup (sec)"),
    "coordination_sec": A(20, "assumption", "Extra coordination per collection during a task (sec)"),
    "place_sec": A(20, "assumption", "Place one item on the shelf (sec)"),
    "placement_error_rate": A(0.02, "assumption", "Share of items placed in the wrong spot"),
    "correction_min": A(2, "assumption", "Time to fix a misplaced item (min)"),
    "max_detour_m_per_item": A(20, "assumption", "Max extra walking per item to collect during a task (m)"),
    "dedicated_min_batch": A(6, "assumption", "Dedicated: items waiting before a trip"),
    "dedicated_age_trigger_min": A(30, "forum", "Dedicated: oldest item age that triggers a trip (min)", "Stores described collecting every 30 minutes to every hour."),
    "hybrid_backlog_trigger": A(15, "assumption", "Hybrid: items waiting that trigger a dedicated trip"),
    "hybrid_age_trigger_min": A(60, "forum", "Hybrid: oldest item age that triggers a dedicated trip (min)", "Stores described collecting every 30 minutes to every hour."),
    "age_priority_weight": A(0.2, "assumption", "How much item age raises pickup priority"),
    "deadline_buffer_min": A(3, "assumption", "Safety buffer before a task deadline (min)"),
    "operating_days": A(363, "assumption", "Operating days per year"),
    "hourly_labor_cost": A(20, "assumption", "Hourly labor cost ($)"),
}

workers = [
    {"id": "W1", "name": "Style TM", "start": 0, "end": 480, "home": "STYLE", "departments": ["Style"],
     "tasks": [{"label": "Push Style freight", "start": "BR", "dest": "STYLE", "every": 120, "work": 40, "window": 90, "cart_load": 4, "offset": 10},
               {"label": "Fitting room recovery", "dest": "STYLE", "every": 60, "work": 20, "window": 45, "offset": 40},
               {"label": "Break", "dest": "BRK", "every": 240, "work": 15, "window": 30, "offset": 115, "pickup": "after", "return_home": True}, {"label": "Backup cashier", "dest": "CL", "every": 120, "work": 15, "window": 40, "offset": 70, "pickup": "after", "return_home": True}]},
    {"id": "W2", "name": "Hardlines TM", "start": 0, "end": 480, "home": "HOME", "departments": ["Home", "Kitchen", "Seasonal", "Toys"],
     "tasks": [{"label": "Push Home freight", "start": "BR", "dest": "HOME", "every": 90, "work": 35, "window": 80, "cart_load": 5, "offset": 5},
               {"label": "Fill Toys backstock", "start": "BR", "dest": "TOYS", "every": 120, "work": 25, "window": 90, "cart_load": 5, "offset": 50},
               {"label": "Break", "dest": "BRK", "every": 240, "work": 15, "window": 30, "offset": 130, "pickup": "after", "return_home": True}]},
    {"id": "W3", "name": "Market & Beauty TM", "start": 0, "end": 480, "home": "MARKET", "departments": ["Market", "Beauty"],
     "tasks": [{"label": "Fill Market", "start": "BR", "dest": "MARKET", "every": 60, "work": 25, "window": 50, "cart_load": 5, "offset": 0},
               {"label": "Zone Beauty", "dest": "BEAUTY", "every": 90, "work": 15, "window": 60, "offset": 30},
               {"label": "Break", "dest": "BRK", "every": 240, "work": 15, "window": 30, "offset": 145, "pickup": "after", "return_home": True}, {"label": "Backup cashier", "dest": "CL", "every": 120, "work": 15, "window": 40, "offset": 100, "pickup": "after", "return_home": True}]},
    {"id": "W4", "name": "Electronics TM", "start": 0, "end": 480, "home": "ELEC", "departments": ["Electronics"],
     "tasks": [{"label": "Electronics fulfillment", "start": "BR", "dest": "ELEC", "every": 45, "work": 15, "window": 40, "cart_load": 3, "offset": 0},
               {"label": "Break", "dest": "BRK", "every": 240, "work": 15, "window": 30, "offset": 160, "pickup": "after", "return_home": True}]},
]

base = {
    "name": "Medium volume",
    "description": "Fictional one-floor store, 8-hour shift, four floor team members. About 230 reshop items.",
    "seed": 7,
    "target_reduction": 0.20,
    "clock_start": "14:00",
    "store": store,
    "workers": workers,
    "arrivals": {"start": 0, "hourly_rate": [18, 22, 26, 30, 34, 38, 34, 26],
                 "dept_weights": {"Style": 0.30, "Beauty": 0.12, "Home": 0.15, "Kitchen": 0.08,
                                  "Seasonal": 0.08, "Electronics": 0.07, "Toys": 0.10, "Market": 0.10}},
    "assumptions": assumptions,
}

out = pathlib.Path(__file__).resolve().parent.parent / "scenarios"
out.mkdir(exist_ok=True)
for key, name, mult, desc in [("low", "Low volume", 0.5, "About 115 reshop items."),
                              ("medium", "Medium volume", 1.0, "About 230 reshop items."),
                              ("high", "High volume", 1.7, "About 390 reshop items, like a busy weekend or after a holiday.")]:
    s = copy.deepcopy(base)
    s["name"] = name
    s["description"] = "Fictional one-floor store, 8-hour shift, four floor team members. " + desc
    s["assumptions"]["arrival_volume_multiplier"]["value"] = mult
    (out / f"{key}.json").write_text(json.dumps(s))
print("wrote", [p.name for p in out.glob("*.json")])
