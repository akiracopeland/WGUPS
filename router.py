# Routing algorithm: Constraint-aware nearest-neighbor + bounded 2-opt
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
from models import Package, Truck
from util import parse_deadline, miles_to_minutes

def distance(M: List[List[float]], a:int, b:int) -> float:
    return M[a][b]

def choose_next_stop(M, current_loc:int, current_time:datetime, mph:float,
                     remaining_ids: List[int],
                     packages: Dict[int, Package]) -> Tuple[int, List[int], int]:
    # Group remaining package IDs by location
    by_loc: Dict[int, List[int]] = {}
    for pid in remaining_ids:
        loc = packages[pid].location_id
        by_loc.setdefault(loc, []).append(pid)

    best_score = float('inf')
    best_loc = None
    best_ids = []
    best_travel_min = 0

    for loc, ids in by_loc.items():
        miles = distance(M, current_loc, loc)
        travel_min = miles_to_minutes(miles, mph)
        arrival = current_time + timedelta(minutes=travel_min)

        # Deadline penalty: zero if on time; grows linearly with minutes late
        penalty = 0.0
        for pid in ids:
            p = packages[pid]
            dlt = parse_deadline(p.deadline)  # returns a time or None for EOD
            if dlt is not None:
                dl_dt = current_time.replace(hour=dlt.hour, minute=dlt.minute, second=0, microsecond=0)
                minutes_late = int((arrival - dl_dt).total_seconds() // 60)
                if minutes_late > 0:
                    penalty += minutes_late * 5.0  # weight

        score = miles + penalty
        if score < best_score:
            best_score = score
            best_loc = loc
            best_ids = ids
            best_travel_min = travel_min

    return best_loc, best_ids, best_travel_min

def two_opt_bounded(route: List[int], M: List[List[float]], limit:int=16) -> None:
    # In-place bounded 2-opt to smooth the path
    n = len(route)
    if n < 4 or limit <= 0:
        return
    improvements = 0
    improved = True
    while improved and improvements < limit:
        improved = False
        for i in range(1, n-2):
            for j in range(i+1, n-1):
                a, b = route[i-1], route[i]
                c, d = route[j], route[j+1]
                cur = M[a][b] + M[c][d]
                alt = M[a][c] + M[b][d]
                if alt + 1e-9 < cur:
                    route[i:j+1] = reversed(route[i:j+1])
                    improvements += 1
                    improved = True
                    if improvements >= limit:
                        return

def build_route_for_truck(truck: Truck, M: List[List[float]], packages: Dict[int, Package],
                          hub_id:int,
                          time_gates: Dict[int, datetime]) -> None:
    remaining = list(truck.carried)
    route = [hub_id]
    current_loc = hub_id
    t = truck.depart_time
    miles_total = 0.0

    def feasible(pid:int, now:datetime) -> bool:
        gate = time_gates.get(pid)
        return (gate is None) or (now >= gate)

    while remaining:
        feasible_ids = [pid for pid in remaining if feasible(pid, t)]
        if not feasible_ids:
            # Advance time to earliest gate among remaining
            next_gate = min(time_gates[pid] for pid in remaining if time_gates.get(pid) is not None)
            t = next_gate
            feasible_ids = [pid for pid in remaining if feasible(pid, t)]

        next_loc, ids_here, travel_min = choose_next_stop(M, current_loc, t, truck.speed_mph,
                                                          feasible_ids, packages)
        # Travel
        miles = M[current_loc][next_loc]
        miles_total += miles
        t = t + timedelta(minutes=travel_min)
        route.append(next_loc)

        # Deliver all packages at this location
        for pid in ids_here:
            p = packages[pid]
            p.status = 'DELIVERED'
            p.delivered_at = t
            packages[pid] = p
            remaining.remove(pid)

        # Self-adjust (bounded 2-opt)
        two_opt_bounded(route, M, limit=16)
        current_loc = next_loc

    # Return to hub
    miles_total += M[current_loc][hub_id]
    route.append(hub_id)
    truck.route = route
    truck.miles = miles_total
    truck.return_time = t  # arrival at last delivery; return time can be derived if needed
