"""simulator.py

This module ties everything together:

1) Parse package constraints (truck-only, deliver-together, time-gated availability).
2) Assign packages to trucks (capacity 16).
3) Simulate each truck's route to compute delivery timestamps.

The CLI (cli.py) uses `run_day()` to produce final delivery times and total miles.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Dict, List, Tuple, Callable, Optional, Set
import re

from models import Package, Truck
from router import build_route_for_truck


# WGUPS defaults from the rubric / project prompt
START_TIME = datetime.combine(datetime.today().date(), time(8, 0))
SPEED_MPH = 18.0
CAPACITY = 16


# -------------------------
# Constraint parsing
# -------------------------

@dataclass(frozen=True)
class AddressCorrection:
    package_id: int
    effective_time: datetime
    new_address: str
    new_zip: str


def parse_time_gates(packages: Dict[int, Package]) -> Tuple[Dict[int, datetime], List[AddressCorrection]]:
    """Parse time-related constraints from package notes.

    Returns:
      - time_gates: earliest time a package can leave the hub
      - corrections: address corrections that become valid at a given time
    """
    time_gates: Dict[int, datetime] = {}
    corrections: List[AddressCorrection] = []

    for pid, p in packages.items():
        note = (p.note or '').lower()

        # Package #9 special case in the standard WGUPS dataset:
        # "Wrong address listed" and corrected at 10:20.
        if pid == 9 and 'wrong address' in note:
            effective = START_TIME.replace(hour=10, minute=20)
            time_gates[pid] = effective
            corrections.append(
                AddressCorrection(
                    package_id=9,
                    effective_time=effective,
                    new_address='410 S State St',
                    new_zip='84111',
                )
            )

        # Delayed packages often say something like:
        # "Delayed on flight---will not arrive to depot until 9:05 am"
        if 'delayed' in note:
            m = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)?', note)
            if m:
                hh = int(m.group(1))
                mm = int(m.group(2))
                ampm = (m.group(3) or '').lower()
                hour = hh
                if ampm == 'pm' and hh != 12:
                    hour = hh + 12
                if ampm == 'am' and hh == 12:
                    hour = 0
                time_gates[pid] = START_TIME.replace(hour=hour, minute=mm)
            else:
                # If the note doesn't include a time, use the common WGUPS delay time.
                time_gates[pid] = START_TIME.replace(hour=9, minute=5)

    return time_gates, corrections


def parse_constraints(packages: Dict[int, Package]) -> Tuple[Set[int], List[Set[int]]]:
    """Parse non-time constraints.

    Returns:
      - truck2_only: package IDs that must be loaded on truck 2
      - groups: "deliver together" groups (each set is a group)
    """
    truck2_only: Set[int] = set()

    # Union-Find for "must be delivered with" relationships.
    parent: Dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for pid, p in packages.items():
        note = (p.note or '')
        low = note.lower()

        if 'can only be on truck 2' in low:
            truck2_only.add(pid)

        if 'must be delivered with' in low:
            # Extract all integers from the note and union them together.
            ids = [int(x) for x in re.findall(r'\d+', note)]
            for other in ids:
                union(pid, other)

    # Build groups from union-find roots.
    groups_map: Dict[int, Set[int]] = {}
    for pid in packages.keys():
        root = find(pid)
        groups_map.setdefault(root, set()).add(pid)

    groups = list(groups_map.values())
    return truck2_only, groups


# -------------------------
# Truck loading / scheduling
# -------------------------

@dataclass
class GroupUnit:
    ids: List[int]
    earliest_deadline_minutes: int  # for sorting (EOD = large)
    requires_truck2: bool


def _deadline_minutes(deadline: str) -> int:
    d = (deadline or '').strip().upper()
    if not d or d == 'EOD' or d == 'END OF DAY':
        return 9999
    # Accept 'HH:MM' and ignore AM/PM in this simplified sorting.
    parts = d.replace('AM', '').replace('PM', '').strip().split(':')
    if len(parts) != 2:
        return 9999
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 9999


def build_group_units(packages: Dict[int, Package], truck2_only: Set[int], groups: List[Set[int]]) -> List[GroupUnit]:
    """Convert union-find groups into sortable GroupUnit objects."""
    units: List[GroupUnit] = []
    for g in groups:
        ids = sorted(g)
        earliest = min(_deadline_minutes(packages[pid].deadline) for pid in ids)
        requires2 = any(pid in truck2_only for pid in ids)
        units.append(GroupUnit(ids=ids, earliest_deadline_minutes=earliest, requires_truck2=requires2))
    return units


def assign_truck_loads(units: List[GroupUnit]) -> Tuple[List[int], List[int], List[int]]:
    """Assign package IDs to three trucks (capacity 16) while honoring constraints."""
    # Split units into: must-go-truck2, urgent, normal.
    must2 = [u for u in units if u.requires_truck2]
    rest = [u for u in units if not u.requires_truck2]

    urgent = [u for u in rest if u.earliest_deadline_minutes != 9999]
    normal = [u for u in rest if u.earliest_deadline_minutes == 9999]

    urgent.sort(key=lambda u: (u.earliest_deadline_minutes, u.ids[0]))
    normal.sort(key=lambda u: u.ids[0])

    t1: List[int] = []
    t2: List[int] = []
    t3: List[int] = []

    def can_fit(truck_list: List[int], unit: GroupUnit) -> bool:
        return len(truck_list) + len(unit.ids) <= CAPACITY

    # 1) Place all truck2-only units on truck2.
    for u in must2:
        if can_fit(t2, u):
            t2.extend(u.ids)
        else:
            # If truck2 is full, spill to truck3 (still honors "truck2 only" in most datasets;
            # the standard WGUPS dataset should not overflow if inputs are correct).
            t3.extend(u.ids)

    # 2) Distribute urgent units across truck1 and truck2, keeping capacity.
    for u in urgent:
        # Prefer the truck with more remaining space.
        if can_fit(t1, u) and (CAPACITY - len(t1) >= CAPACITY - len(t2) or not can_fit(t2, u)):
            t1.extend(u.ids)
        elif can_fit(t2, u):
            t2.extend(u.ids)
        else:
            t3.extend(u.ids)

    # 3) Fill remaining space with normal units.
    for u in normal:
        if can_fit(t1, u):
            t1.extend(u.ids)
        elif can_fit(t2, u):
            t2.extend(u.ids)
        else:
            t3.extend(u.ids)

    return t1, t2, t3


def _max_gate_time(package_ids: List[int], time_gates: Dict[int, datetime], default: datetime) -> datetime:
    latest = default
    for pid in package_ids:
        gate = time_gates.get(pid)
        if gate and gate > latest:
            latest = gate
    return latest


def apply_address_corrections(
    now: datetime,
    packages: Dict[int, Package],
    corrections: List[AddressCorrection],
    location_lookup: Optional[Callable[[str], int]],
) -> None:
    """Apply any address corrections that are effective at or before `now`."""
    for c in corrections:
        if now >= c.effective_time:
            p = packages.get(c.package_id)
            if not p:
                continue
            p.address = c.new_address
            p.zip = c.new_zip
            if location_lookup:
                p.location_id = location_lookup(c.new_address)
            packages[c.package_id] = p


def run_day(
    hub_id: int,
    M: List[List[float]],
    packages: Dict[int, Package],
    location_lookup: Optional[Callable[[str], int]] = None,
) -> Tuple[Tuple[Truck, Truck, Truck], float]:
    """Run the full-day simulation and return (trucks, total_miles).

    `location_lookup` is optional, but if provided it allows the simulator to
    update package #9's corrected address to the correct location_id.
    """
    time_gates, corrections = parse_time_gates(packages)
    truck2_only, groups = parse_constraints(packages)
    units = build_group_units(packages, truck2_only, groups)

    t1_ids, t2_ids, t3_ids = assign_truck_loads(units)
    # ---- Rebalance for time-gated packages ----
    # We want at least one truck to leave at 8:00 with non-delayed packages.
    # In the standard WGUPS dataset:
    #   - delayed packages become available at 9:05
    #   - package #9 becomes deliverable at 10:20 (wrong address corrected)
    # If a late-gated package ends up on truck1, it would unnecessarily delay the whole truck.
    #
    # We therefore move any "late-gated" delivery groups off truck1:
    #   - gates > 10:00 -> truck3
    #   - gates > 8:00  -> truck2 (if it fits), otherwise truck3
    #
    # Because we build deliver-together groups, we move whole groups, not individual packages.
    pid_to_unit = {}
    for u in units:
        for pid in u.ids:
            pid_to_unit[pid] = u

    def unit_gate_time(u: GroupUnit) -> datetime:
        latest = START_TIME
        for pid in u.ids:
            gate = time_gates.get(pid)
            if gate and gate > latest:
                latest = gate
        return latest

    def remove_unit_from(truck_list: List[int], u: GroupUnit) -> None:
        for pid in u.ids:
            if pid in truck_list:
                truck_list.remove(pid)

    def add_unit_to(truck_list: List[int], u: GroupUnit) -> bool:
        if len(truck_list) + len(u.ids) > CAPACITY:
            return False
        truck_list.extend(u.ids)
        return True

    # Move gated units off truck1.
    t1_units = []
    seen = set()
    for pid in t1_ids:
        u = pid_to_unit[pid]
        if id(u) not in seen:
            t1_units.append(u)
            seen.add(id(u))

    for u in t1_units:
        gate = unit_gate_time(u)
        if gate <= START_TIME:
            continue
        # Do not move truck2-only groups away from truck2 requirement; but these are on truck1 only if overflow.
        remove_unit_from(t1_ids, u)

        if gate >= START_TIME.replace(hour=10, minute=0):
            add_unit_to(t3_ids, u)
        else:
            # Prefer truck2 for 9:05-type delays if there is room.
            if not add_unit_to(t2_ids, u):
                add_unit_to(t3_ids, u)

    # Back-fill truck1 from truck3 with earliest-deadline, non-gated units.
    # (Keeps truck1 utilization high without delaying departure.)
    t3_units = []
    seen = set()
    for pid in t3_ids:
        u = pid_to_unit[pid]
        if id(u) not in seen:
            t3_units.append(u)
            seen.add(id(u))

    # Sort by urgency (earliest deadline first).
    t3_units.sort(key=lambda u: (u.earliest_deadline_minutes, u.ids[0]))

    for u in t3_units:
        if len(t1_ids) >= CAPACITY:
            break
        if unit_gate_time(u) > START_TIME:
            continue
        if len(t1_ids) + len(u.ids) <= CAPACITY:
            remove_unit_from(t3_ids, u)
            add_unit_to(t1_ids, u)



    # ---- Tight-deadline fix-up ----
    # Truck2 often departs later (e.g., because of delayed packages). If a 10:30-deadline package
    # is on a late-departing truck, it can miss its deadline even if the routing is reasonable.
    #
    # We do a single, simple fix-up pass:
    #   - move early-deadline units from truck2 -> truck1 when possible
    #   - to make room, move an EOD unit from truck1 -> truck3
    #
    # This keeps the algorithm polynomial and avoids complex search.
    EARLY_DEADLINE = 10 * 60 + 30  # 10:30 in minutes

    # Unique units currently on truck2, sorted by deadline.
    t2_units = []
    seen = set()
    for pid in t2_ids:
        u = pid_to_unit[pid]
        if id(u) not in seen:
            t2_units.append(u)
            seen.add(id(u))
    t2_units.sort(key=lambda u: (u.earliest_deadline_minutes, u.ids[0]))

    # Candidate "moveable" units from truck1 (EOD, not gated).
    def is_moveable_from_t1(u: GroupUnit) -> bool:
        return (u.earliest_deadline_minutes == 9999) and (unit_gate_time(u) <= START_TIME) and (not u.requires_truck2)

    t1_units = []
    seen = set()
    for pid in t1_ids:
        u = pid_to_unit[pid]
        if id(u) not in seen:
            t1_units.append(u)
            seen.add(id(u))

    for u in t2_units:
        if u.earliest_deadline_minutes > EARLY_DEADLINE:
            continue
        if u.requires_truck2:
            continue

        if unit_gate_time(u) > START_TIME:
            # Don't move delayed / late-gated packages onto the early-depart truck.
            continue

        needed = len(u.ids)
        free = CAPACITY - len(t1_ids)
        if free < needed:
            # Move EOD units from truck1 to truck3 until there's space.
            for donor in list(t1_units):
                if free >= needed:
                    break
                if not is_moveable_from_t1(donor):
                    continue
                remove_unit_from(t1_ids, donor)
                add_unit_to(t3_ids, donor)
                free = CAPACITY - len(t1_ids)

        if CAPACITY - len(t1_ids) >= needed:
            # Move the urgent unit t2 -> t1
            remove_unit_from(t2_ids, u)
            add_unit_to(t1_ids, u)

    
    # ---- Sanity: ensure each package ID is assigned exactly once ----
    def _dedupe(seq: List[int]) -> List[int]:
        seen_ids = set()
        out_ids: List[int] = []
        for x in seq:
            if x not in seen_ids:
                out_ids.append(x)
                seen_ids.add(x)
        return out_ids

    t1_ids = _dedupe(t1_ids)
    t2_ids = _dedupe(t2_ids)
    t3_ids = _dedupe(t3_ids)

    assigned = set(t1_ids)
    t2_ids = [pid for pid in t2_ids if pid not in assigned]
    assigned.update(t2_ids)
    t3_ids = [pid for pid in t3_ids if pid not in assigned]
    assigned.update(t3_ids)

    missing = [pid for pid in packages.keys() if pid not in assigned]
    # Any missing packages go on truck3 (it departs latest and usually has flexibility).
    for pid in missing:
        t3_ids.append(pid)

    # Capacity guard: in the standard dataset this should not overflow.
    t1_ids = t1_ids[:CAPACITY]
    t2_ids = t2_ids[:CAPACITY]
    t3_ids = t3_ids[:CAPACITY]

    # Create trucks with provisional depart times (we may bump these due to gate times / driver availability).
    t1 = Truck(id=1, speed_mph=SPEED_MPH, capacity=CAPACITY, depart_time=START_TIME, route=[], carried=t1_ids)
    t2 = Truck(id=2, speed_mph=SPEED_MPH, capacity=CAPACITY, depart_time=START_TIME, route=[], carried=t2_ids)
    t3 = Truck(id=3, speed_mph=SPEED_MPH, capacity=CAPACITY, depart_time=START_TIME, route=[], carried=t3_ids)

    # A truck cannot leave before the latest "gate" time of any package on it.
    t1.depart_time = _max_gate_time(t1.carried, time_gates, t1.depart_time)
    t2.depart_time = _max_gate_time(t2.carried, time_gates, t2.depart_time)

    # Apply any corrections that are already effective when trucks 1 and 2 depart.
    apply_address_corrections(t1.depart_time, packages, corrections, location_lookup)
    apply_address_corrections(t2.depart_time, packages, corrections, location_lookup)

    # Mark each package with the time its truck leaves the hub (used for time-based status queries in CLI).
    for pid in t1.carried:
        packages[pid].depart_time = t1.depart_time
    for pid in t2.carried:
        packages[pid].depart_time = t2.depart_time

    # Build routes for trucks 1 and 2 first (two drivers start the day).
    build_route_for_truck(t1, M, packages, hub_id, time_gates)
    build_route_for_truck(t2, M, packages, hub_id, time_gates)

    # The third truck can only depart when a driver returns.
    earliest_driver_return = min(t1.return_time, t2.return_time)

    # It also can't depart before the latest gate among its packages.
    t3.depart_time = max(
        earliest_driver_return,
        _max_gate_time(t3.carried, time_gates, START_TIME),
    )

    # Apply corrections effective by truck3's departure (this is where package #9 usually gets fixed).
    apply_address_corrections(t3.depart_time, packages, corrections, location_lookup)

    for pid in t3.carried:
        packages[pid].depart_time = t3.depart_time

    build_route_for_truck(t3, M, packages, hub_id, time_gates)

    total_miles = (t1.miles or 0.0) + (t2.miles or 0.0) + (t3.miles or 0.0)
    return (t1, t2, t3), total_miles
