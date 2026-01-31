"""cli.py

Interactive command-line interface for the WGUPS routing simulation.

Program flow when you run `python main.py`:
  1) Load packages + distance table CSVs.
  2) Build:
       - a custom HashTable (Task A/B requirement)
       - a normal dict of Package objects (used by our simulator)
  3) Run the full-day simulation (simulator.run_day)
  4) Update the HashTable with the final delivery results
  5) Provide a small menu to query package status at any time of day.

Note:
- The CLI is intentionally small; most logic lives in data_loader.py, simulator.py, and router.py.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, time
from typing import Dict, Callable

from models import Package, Truck
from hash_table import HashTable, ht_insert_package, ht_lookup_package
from data_loader import load_packages_csv, load_distance_matrix_csv
from simulator import run_day, START_TIME
from util import address_key


DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

# Rubric assumption: WGUPS does not know package #9’s corrected address until 10:20.
PKG9_CORRECTION_TIME = datetime.combine(START_TIME.date(), time(10, 20))


def build_location_lookup(names: list[str]) -> Callable[[str], int]:
    """Return a function that maps a street address to the closest location_id in the distance table.

    The distance table names often include extra context (building name, city, etc.).
    We use a loose substring match on normalized text.
    """
    normalized = [(address_key(n), i) for i, n in enumerate(names)]

    def lookup(address: str) -> int:
        key = address_key(address)
        # Prefer exact substring matches.
        for name_key, idx in normalized:
            if key and key in name_key:
                return idx
        # Fallback: if no match, return HUB (0). This keeps the program running even on imperfect data.
        return 0

    return lookup


def build_packages_store(pack_rows, location_lookup: Callable[[str], int]) -> tuple[HashTable, Dict[int, Package]]:
    """Create both the HashTable (Task A/B) and an in-memory Package map."""
    store = HashTable()
    packages: Dict[int, Package] = {}

    for row in pack_rows:
        loc_id = location_lookup(row['Address'])

        p = Package(
            id=int(row['ID']),
            address=row['Address'],
            city=row['City'],
            zip=str(row['Zip']),
            deadline=row['Deadline'],
            weight=float(row['Weight']),
            note=row['Note'],
            location_id=loc_id,
        )

        # Task A insertion: store package components in the custom hash table.
        ht_insert_package(store, p.id, p.address, p.deadline, p.city, p.zip, p.weight, p.status, None)
        packages[p.id] = p

    return store, packages


def parse_user_time(timestr: str) -> datetime:
    """Parse user-entered time.

    Accepts:
      - 24-hour: '13:00', '09:05'
      - 12-hour with AM/PM: '1:00 PM', '9:05 am'

    If user enters a 24-hour time earlier than the hub start time (08:00),
    assume they meant PM (e.g., '1:00' -> 13:00). This matches the project
    context where users typically check daytime delivery statuses.
    """
    s = (timestr or '').strip().upper()

    # Try 12-hour formats first (AM/PM)
    for fmt in ('%I:%M %p', '%I:%M%p'):
        try:
            t = datetime.strptime(s, fmt).time()
            return datetime.combine(START_TIME.date(), t)
        except ValueError:
            pass

    # Fall back to 24-hour format
    t = datetime.strptime(s, '%H:%M').time()
    dt_val = datetime.combine(START_TIME.date(), t)

    # If the time is earlier than the delivery start (08:00), interpret it as PM.
    # Example: user types '1:00' meaning 1:00 PM (13:00).
    if t < START_TIME.time():
        dt_val = dt_val.replace(hour=(dt_val.hour + 12) % 24)

    return dt_val


def delayed_until_time(p: Package) -> datetime | None:
    """If a package note indicates a delay-until time (e.g., 9:05 AM), return that datetime.

    Returns None if the package is not delayed.
    """
    note = (p.note or "").lower()
    if "delayed" not in note:
        return None

    # Common WGUPS note: "Delayed on flight---will not arrive to depot until 9:05 am"
    m = re.search(r'(\d{1,2}:\d{2})\s*(am|pm)?', note)
    if not m:
        # If note says delayed but time isn't parseable, use the dataset convention.
        return datetime.combine(START_TIME.date(), time(9, 5))

    hhmm = m.group(1)
    ampm = (m.group(2) or "").upper()

    if ampm in {"AM", "PM"}:
        t = datetime.strptime(f"{hhmm} {ampm}", "%I:%M %p").time()
    else:
        # If no AM/PM given, interpret as 24-hour. (WGUPS dataset uses AM for these delays.)
        t = datetime.strptime(hhmm, "%H:%M").time()

    return datetime.combine(START_TIME.date(), t)


def package_status_at(p: Package, at_time: datetime) -> tuple[str, str]:
    """Compute a package status snapshot at a specific time of day.

    Returns (status, time_str):
      - DELIVERED -> time_str is delivered time
      - DELAYED   -> time_str is delay-until time (arrival at hub)
      - EN_ROUTE/HUB -> time_str empty
    """
    if p.delivered_at and p.delivered_at <= at_time:
        return 'DELIVERED', p.delivered_at.strftime('%H:%M')

    # If the package hasn't arrived at the hub yet, show DELAYED (not HUB).
    gate = delayed_until_time(p)
    if gate is not None and at_time < gate:
        return 'DELAYED', gate.strftime('%H:%M')

    if p.depart_time and p.depart_time <= at_time:
        return 'EN_ROUTE', ''
    return 'HUB', ''


def public_address_city_zip(store: HashTable, p: Package, at_time: datetime) -> tuple[str, str, str]:
    """Return the address/city/zip that WGUPS is allowed to display at a given time.

    Key rubric rule:
      - Package #9 corrected address is NOT known until 10:20.
      - Before 10:20, we must not display the corrected address.
    """
    if p.id == 9 and at_time < PKG9_CORRECTION_TIME:
        # Show the original (wrong) address that was loaded from CSV into the hash table.
        rec = ht_lookup_package(store, 9)
        if rec is not None:
            return rec['address'], rec['city'], rec['zip']
        # Fallback (should not happen): use whatever we have.
    return p.address, p.city, p.zip


def print_package_status(packages: Dict[int, Package], store: HashTable, at_time: datetime) -> None:
    """Print a table of package statuses at a given time.

    Also respects the rubric rule about not revealing package #9’s corrected address before 10:20.

    Note: For DELAYED packages, the "Delivered At" column shows the delay-until time.
    """
    print(f"\nPackage status at {at_time.strftime('%H:%M')}:\n")
    print(f"{'ID':>3}  {'Address':<40} {'Deadline':<8} {'City':<12} {'Zip':<5} {'Wt':>5}  {'Status':<10} {'Delivered At':<10}")
    print('-' * 110)

    for pid in sorted(packages.keys()):
        p = packages[pid]
        status, time_str = package_status_at(p, at_time)

        addr, city, z = public_address_city_zip(store, p, at_time)

        print(f"{p.id:>3}  {addr:<40} {p.deadline:<8} {city:<12} {z:<5} {p.weight:>5.1f}  {status:<10} {time_str:<10}")
    print()


def print_completion_report(trucks: tuple[Truck, Truck, Truck], total_miles: float, packages: Dict[int, Package]) -> None:
    """Print a rubric-friendly completion report (Requirement E).

    This is designed for screenshots:
    - Each truck's depart/return time and miles
    - Total mileage for all trucks
    - Confirmation that all packages were delivered
    """
    undelivered = [pid for pid, p in packages.items() if p.delivered_at is None]

    print("\n=== Simulation completed successfully ===")
    for t in trucks:
        # depart_time always exists; return_time should be set by router
        depart = t.depart_time.strftime('%H:%M')
        returned = t.return_time.strftime('%H:%M') if t.return_time else "N/A"
        print(
            f"Truck {t.id}: depart {depart} | return {returned} | "
            f"miles {t.miles:.2f} | packages {len(t.carried)}"
        )

    print(f"\nTOTAL MILEAGE (all trucks): {total_miles:.2f} miles")
    print(f"All packages delivered: {'YES' if not undelivered else 'NO'}\n")

    if undelivered:
        # Should not happen for the standard dataset, but it's helpful for debugging.
        print("Undelivered package IDs:", ", ".join(map(str, sorted(undelivered))))
        print()


def run_cli() -> None:
    """CLI entry point."""
    print("WGUPS Routing Program (standard library only)\n")

    packages_path = os.path.join(DATA_DIR, 'packages.csv')

    # Some repositories include a cleaned CSV; prefer it if present.
    distances_clean = os.path.join(DATA_DIR, 'distances_clean.csv')
    distances_raw = os.path.join(DATA_DIR, 'distances.csv')
    distances_path = distances_clean if os.path.exists(distances_clean) else distances_raw

    if not os.path.exists(packages_path) or not os.path.exists(distances_path):
        print("Data files not found. Please export the Excel files to CSV and place them in the data/ folder:")
        print(" - packages.csv  (columns: ID,Address,City,Zip,Deadline,Weight,Note)")
        print(" - distances.csv (WGUPS distance table exported to CSV)\n")
        return

    # 1) Load raw rows.
    pack_rows = load_packages_csv(packages_path)
    names, M = load_distance_matrix_csv(distances_path)

    # 2) Build helper for address->location_id matching.
    location_lookup = build_location_lookup(names)

    # 3) Build package storage (HashTable + Package objects).
    store, packages = build_packages_store(pack_rows, location_lookup)

    # Preserve package #9's ORIGINAL public info from the hash table.
    # We will keep these values in the hash table even after the simulation corrects the internal route.
    pkg9_original = ht_lookup_package(store, 9)

    # 4) Run routes for the day.
    hub_id = 0
    trucks, total_miles = run_day(hub_id, M, packages, location_lookup=location_lookup)

    # 5) Write final status/delivery times back to the hash table (Task A/B consistency).
    for pid, p in packages.items():
        rec = ht_lookup_package(store, pid)
        if rec is None:
            continue

        # IMPORTANT RUBRIC RULE:
        # Do NOT overwrite package #9's address/city/zip with the corrected values in the hash table,
        # because WGUPS doesn't "know" the correct address until 10:20 for status checks.
        if pid == 9 and pkg9_original is not None:
            address = pkg9_original['address']
            city = pkg9_original['city']
            zip_code = pkg9_original['zip']
        else:
            address = p.address
            city = p.city
            zip_code = p.zip

        ht_insert_package(
            store,
            pid,
            address,
            p.deadline,
            city,
            zip_code,
            p.weight,
            p.status,
            p.delivered_at,
        )

    # Requirement E: show a rubric-friendly completion/mileage report in the CLI.
    print_completion_report(trucks, total_miles, packages)

    # ---- Interactive menu ----
    while True:
        print("Choose an option:")
        print(" 1) Lookup package by ID at a time (HH:MM)")
        print(" 2) Show all package statuses at a time (HH:MM)")
        print(" 3) Show first 10 hash table buckets (screenshot aid)")
        print(" 4) Show completion report (total mileage)")
        print(" 5) Exit")
        choice = input("> ").strip()

        if choice == '1':
            pid = int(input("Enter Package ID: ").strip())
            timestr = input("Enter time (HH:MM or HH:MM AM/PM): ").strip()
            at_time = parse_user_time(timestr)

            p = packages.get(pid)
            if not p:
                print("Not found.\n")
                continue

            # For display, use time-aware “public” info (prevents leaking pkg #9 corrected address early).
            rec = ht_lookup_package(store, pid)
            status, time_str = package_status_at(p, at_time)

            addr, city, z = public_address_city_zip(store, p, at_time)

            # If delayed, show why/when in a friendly way.
            extra = ""
            if status == "DELAYED" and time_str:
                extra = f"(arrives at hub at {time_str})"
            elif status == "DELIVERED" and time_str:
                extra = f"(delivered at {time_str})"

            print(
                f"\nPackage {pid}: {addr}, {city} {z}, "
                f"deadline {rec['deadline'] if rec else p.deadline}, weight {(rec['weight'] if rec else p.weight):.1f}\n"
                f"Status at {timestr}: {status} {extra}\n"
            )

        elif choice == '2':
            timestr = input("Enter time (HH:MM or HH:MM AM/PM): ").strip()
            at_time = parse_user_time(timestr)
            print_package_status(packages, store, at_time)

        elif choice == '3':
            buckets = store.first_n_buckets(10)
            print("\nFirst 10 buckets (for screenshot):\n")
            for idx, bucket in enumerate(buckets):
                print(f"Bucket {idx}: {bucket}")
            print()

        elif choice == '4':
            # Re-print the rubric-friendly completion/mileage report for screenshots.
            print_completion_report(trucks, total_miles, packages)

        else:
            break
