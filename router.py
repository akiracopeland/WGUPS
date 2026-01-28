"""router.py

Route building and delivery-time simulation.

High-level idea:
- Start at HUB.
- Repeatedly pick the "best" next location using a nearest-neighbor heuristic.
  - The heuristic is distance + a penalty for being late to any deadline packages
    at that location.
- After we have an ordered list of stops, optionally apply a bounded 2-opt pass
  to reduce total miles.
- Finally, simulate driving the route to compute:
  - delivery times for each package
  - total miles
  - truck return time
"""

from __future__ import annotations

from typing import List, Dict, Tuple
from datetime import datetime, timedelta

from models import Package, Truck
from util import parse_deadline, miles_to_minutes


def choose_next_stop(
    M: List[List[float]],
    current_loc: int,
    current_time: datetime,
    mph: float,
    remaining_ids: List[int],
    packages: Dict[int, Package],
) -> Tuple[int, List[int], int]:
    """Pick the next location to visit.

    Returns:
      (next_location_id, package_ids_at_that_location, travel_minutes)
    """
    # Group remaining packages by location so we can evaluate "visit this location" once.
    by_loc: Dict[int, List[int]] = {}
    for pid in remaining_ids:
        loc = packages[pid].location_id
        by_loc.setdefault(loc, []).append(pid)

    best_score = float('inf')
    best_loc = None
    best_ids: List[int] = []
    best_travel_min = 0

    for loc, ids in by_loc.items():
        miles = M[current_loc][loc]
        travel_min = miles_to_minutes(miles, mph)
        arrival = current_time + timedelta(minutes=travel_min)

        # Deadline penalty: if we'd arrive late to a deadline, increase the score.
        penalty = 0.0
        for pid in ids:
            p = packages[pid]
            dlt = parse_deadline(p.deadline)  # time or None (EOD)
            if dlt is None:
                continue
            dl_dt = arrival.replace(hour=dlt.hour, minute=dlt.minute, second=0, microsecond=0)
            minutes_late = int((arrival - dl_dt).total_seconds() // 60)
            if minutes_late > 0:
                penalty += minutes_late * 5.0  # weight for "late" (tunable)

        score = miles + penalty
        if score < best_score:
            best_score = score
            best_loc = loc
            best_ids = ids
            best_travel_min = travel_min

    # best_loc should always exist if remaining_ids is non-empty.
    return best_loc, best_ids, best_travel_min


def two_opt_bounded(stops: List[int], M: List[List[float]], hub_id: int, limit: int = 32) -> List[int]:
    """A bounded 2-opt optimization pass.

    We apply 2-opt to the *stop list* (no hub at ends), then return a new list.
    """
    if len(stops) < 4 or limit <= 0:
        return stops[:]

    route = stops[:]
    improvements = 0
    improved = True

    def route_miles(order: List[int]) -> float:
        miles = 0.0
        cur = hub_id
        for loc in order:
            miles += M[cur][loc]
            cur = loc
        miles += M[cur][hub_id]
        return miles

    best_miles = route_miles(route)

    while improved and improvements < limit:
        improved = False
        n = len(route)
        for i in range(0, n - 2):
            for j in range(i + 1, n - 1):
                candidate = route[:]
                candidate[i : j + 1] = reversed(candidate[i : j + 1])
                cand_miles = route_miles(candidate)
                if cand_miles + 1e-9 < best_miles:
                    route = candidate
                    best_miles = cand_miles
                    improvements += 1
                    improved = True
                    if improvements >= limit:
                        return route
    return route


def _simulate(
    stops: List[int],
    truck: Truck,
    M: List[List[float]],
    packages: Dict[int, Package],
    hub_id: int,
) -> Tuple[float, datetime, Dict[int, datetime]]:
    """Simulate driving HUB -> stops -> HUB.

    Returns:
      (total_miles, return_time, delivered_times_by_package_id)

    Note: This does not mutate packages; it only computes.
    """
    t = truck.depart_time
    cur = hub_id
    miles_total = 0.0
    delivered_times: Dict[int, datetime] = {}

    # Precompute: which package IDs are delivered at each stop.
    by_loc: Dict[int, List[int]] = {}
    for pid in truck.carried:
        by_loc.setdefault(packages[pid].location_id, []).append(pid)

    for loc in stops:
        miles = M[cur][loc]
        miles_total += miles
        t = t + timedelta(minutes=miles_to_minutes(miles, truck.speed_mph))
        for pid in by_loc.get(loc, []):
            delivered_times[pid] = t
        cur = loc

    # Return to hub.
    miles_total += M[cur][hub_id]
    t = t + timedelta(minutes=miles_to_minutes(M[cur][hub_id], truck.speed_mph))
    return miles_total, t, delivered_times


def _late_count(delivered_times: Dict[int, datetime], packages: Dict[int, Package]) -> int:
    """How many packages miss their deadline?"""
    late = 0
    for pid, dt in delivered_times.items():
        dlt = parse_deadline(packages[pid].deadline)
        if dlt is None:
            continue
        deadline_dt = dt.replace(hour=dlt.hour, minute=dlt.minute, second=0, microsecond=0)
        if dt > deadline_dt:
            late += 1
    return late


def build_route_for_truck(
    truck: Truck,
    M: List[List[float]],
    packages: Dict[int, Package],
    hub_id: int,
    time_gates: Dict[int, datetime],
    enable_two_opt: bool = True,
) -> None:
    """Compute a truck route and mutate `packages` with delivery times.

    Flow:
      1) Build a greedy stop order (nearest-neighbor with deadline penalty).
      2) Optionally run a bounded 2-opt pass if it improves miles without increasing lateness.
      3) Simulate the final route to compute delivery timestamps and total miles.
    """
    # 1) Build the greedy stop order.
    remaining = list(truck.carried)
    stops: List[int] = []
    cur = hub_id
    t = truck.depart_time

    def is_available(pid: int, now: datetime) -> bool:
        gate = time_gates.get(pid)
        return gate is None or now >= gate

    while remaining:
        # If some packages are time-gated (delayed / wrong address), we may need to wait.
        feasible = [pid for pid in remaining if is_available(pid, t)]
        if not feasible:
            # Jump time forward to the earliest gate of the remaining packages.
            t = min(time_gates[pid] for pid in remaining if time_gates.get(pid) is not None)
            feasible = [pid for pid in remaining if is_available(pid, t)]

        next_loc, ids_here, travel_min = choose_next_stop(M, cur, t, truck.speed_mph, feasible, packages)

        # Record the stop, then advance our working clock & location.
        stops.append(next_loc)
        t = t + timedelta(minutes=travel_min)
        cur = next_loc

        # Remove all packages delivered at that location from the remaining list.
        for pid in ids_here:
            if pid in remaining:
                remaining.remove(pid)

    # De-duplicate stops (multiple packages share a location).
    # The greedy builder can add the same location more than once if feasibility changes; remove repeats while preserving order.
    seen = set()
    deduped_stops = []
    for loc in stops:
        if loc not in seen:
            deduped_stops.append(loc)
            seen.add(loc)
    stops = deduped_stops

    # 2) Optional 2-opt optimization (only accept if it helps without making deadlines worse).
    if enable_two_opt and len(stops) >= 4:
        base_miles, _, base_delivered = _simulate(stops, truck, M, packages, hub_id)
        base_late = _late_count(base_delivered, packages)

        opt_stops = two_opt_bounded(stops, M, hub_id, limit=32)
        opt_miles, _, opt_delivered = _simulate(opt_stops, truck, M, packages, hub_id)
        opt_late = _late_count(opt_delivered, packages)

        if opt_miles + 1e-9 < base_miles and opt_late <= base_late:
            stops = opt_stops

    # 3) Final simulation and mutation of truck + packages.
    miles_total, return_time, delivered_times = _simulate(stops, truck, M, packages, hub_id)

    # Build the full "route" list including hub on both ends (for display/debug).
    truck.route = [hub_id] + stops + [hub_id]
    truck.miles = miles_total
    truck.return_time = return_time

    # Update each package delivered by this truck.
    for pid in truck.carried:
        p = packages[pid]
        p.status = 'DELIVERED'
        p.delivered_at = delivered_times.get(pid)  # should always exist
        packages[pid] = p
