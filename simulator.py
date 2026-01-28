# Simulation: assign trucks, handle time-gated constraints, and run routes
from datetime import datetime, time, timedelta
from typing import Dict, List, Tuple
from models import Package, Truck
from router import build_route_for_truck

START_TIME = datetime.combine(datetime.today().date(), time(8,0))
SPEED_MPH = 18.0
CAPACITY = 16

def parse_special_notes(packages: Dict[int, Package]) -> Dict[int, datetime]:
    gates: Dict[int, datetime] = {}
    for pid, p in packages.items():
        note = (p.note or '').lower()
        if 'wrong address' in note and pid == 9:
            gates[pid] = START_TIME.replace(hour=10, minute=20)
        if 'delayed' in note:
            import re
            m = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)?', note)
            if m:
                hh = int(m.group(1)); mm = int(m.group(2))
                ampm = (m.group(3) or '').lower()
                hour = hh
                if ampm == 'pm' and hh != 12:
                    hour = hh + 12
                if ampm == 'am' and hh == 12:
                    hour = 0
                gates[pid] = START_TIME.replace(hour=hour, minute=mm)
            else:
                gates[pid] = START_TIME.replace(hour=9, minute=5)
    return gates

def assign_initial_truck_loads(packages: Dict[int, Package]) -> Tuple[Truck, Truck, Truck]:
    urgent = []
    normal = []
    for p in packages.values():
        dl = p.deadline.upper().strip()
        if dl != 'EOD' and dl:
            urgent.append(p.id)
        else:
            normal.append(p.id)

    def dl_key(pid:int):
        p = packages[pid]
        s = p.deadline.upper().strip()
        if s == 'EOD' or not s: return (9999, pid)
        hh, mm = s.split(':')
        return (int(hh)*60 + int(mm), pid)

    urgent.sort(key=dl_key)
    normal.sort(key=lambda x: x)

    truck1_ids = []
    truck2_ids = []
    for pid in urgent:
        if len(truck1_ids) < CAPACITY:
            truck1_ids.append(pid)
        elif len(truck2_ids) < CAPACITY:
            truck2_ids.append(pid)
    for pid in normal:
        if len(truck1_ids) < CAPACITY:
            truck1_ids.append(pid)
        elif len(truck2_ids) < CAPACITY:
            truck2_ids.append(pid)

    assigned = set(truck1_ids + truck2_ids)
    remaining = [p.id for p in packages.values() if p.id not in assigned]

    truck1 = Truck(id=1, speed_mph=SPEED_MPH, capacity=CAPACITY, depart_time=START_TIME,
                   route=[], carried=truck1_ids)
    truck2 = Truck(id=2, speed_mph=SPEED_MPH, capacity=CAPACITY, depart_time=START_TIME,
                   route=[], carried=truck2_ids)
    truck3 = Truck(id=3, speed_mph=SPEED_MPH, capacity=CAPACITY, depart_time=START_TIME.replace(hour=10, minute=20),
                   route=[], carried=remaining)
    return truck1, truck2, truck3

def run_day(hub_id:int, M, packages: Dict[int, Package]):
    gates = parse_special_notes(packages)
    t1, t2, t3 = assign_initial_truck_loads(packages)

    # Mark packages on trucks as EN_ROUTE at their depart times (for display semantics)
    for pid in t1.carried:
        packages[pid].status = 'EN_ROUTE'
    for pid in t2.carried:
        packages[pid].status = 'EN_ROUTE'
    for pid in t3.carried:
        # truck3 departs later; keep HUB until its depart time in time-aware views
        pass

    # Run routes
    build_route_for_truck(t1, M, packages, hub_id, gates)
    build_route_for_truck(t2, M, packages, hub_id, gates)
    build_route_for_truck(t3, M, packages, hub_id, gates)

    total_miles = (t1.miles or 0) + (t2.miles or 0) + (t3.miles or 0)
    return (t1, t2, t3), total_miles
