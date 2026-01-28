# Simple CLI for WGUPS program
import os
from datetime import datetime
from typing import Dict
from models import Package
from hash_table import HashTable, ht_insert_package, ht_lookup_package
from data_loader import load_packages_csv, load_distance_matrix_csv
from simulator import run_day, START_TIME

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

def build_packages_store(pack_rows, loc_index) -> (HashTable, Dict[int, Package]):
    store = HashTable()
    packages: Dict[int, Package] = {}
    for row in pack_rows:
        # location id best-effort match
        addr = row['Address'].strip()
        loc_id = 0
        for name, idx in loc_index.items():
            if addr == name or addr in name or name in addr:
                loc_id = idx
                break
        p = Package(id=int(row['ID']), address=row['Address'], city=row['City'], zip=str(row['Zip']),
                    deadline=row['Deadline'], weight=float(row['Weight']), note=row['Note'], location_id=loc_id)
        # Use required Task A insertion function
        ht_insert_package(store, p.id, p.address, p.deadline, p.city, p.zip, p.weight, p.status, None)
        packages[p.id] = p
    return store, packages

def print_package_status(packages: Dict[int, Package], at_time: datetime):
    print(f"\nPackage status at {at_time.strftime('%H:%M')}:\n")
    print(f"{'ID':>3}  {'Address':<40} {'Deadline':<6} {'City':<12} {'Zip':<5} {'Wt':>5}  {'Status':<10} {'Delivered At':<5}")
    print('-'*100)
    for pid in sorted(packages.keys()):
        p = packages[pid]
        status = 'HUB'
        delivered_at = ''
        if p.delivered_at and p.delivered_at <= at_time:
            status = 'DELIVERED'
            delivered_at = p.delivered_at.strftime('%H:%M')
        else:
            # if assigned and depart before at_time, show EN_ROUTE
            # (We do not store per-package depart; simple rule: if delivered_at exists and is after at_time, then EN_ROUTE)
            if p.delivered_at and p.delivered_at > at_time:
                status = 'EN_ROUTE'
            else:
                status = p.status
        print(f"{p.id:>3}  {p.address:<40} {p.deadline:<6} {p.city:<12} {p.zip:<5} {p.weight:>5.1f}  {status:<10} {delivered_at:<5}")
    print()

def run_cli():
    print("WGUPS Routing Program (standard library only)\n")
    packages_path = os.path.join(DATA_DIR, 'packages.csv')
    distances_path = os.path.join(DATA_DIR, 'distances.csv')

    if not os.path.exists(packages_path) or not os.path.exists(distances_path):
        print("Data files not found. Please export the Excel files to CSV and place them in the data/ folder:")
        print(" - packages.csv  (columns: ID,Address,City,Zip,Deadline,Weight,Note)")
        print(" - distances.csv (square matrix with names in header row and first column)\n")
        return

    pack_rows = load_packages_csv(packages_path)
    names, M = load_distance_matrix_csv(distances_path)
    loc_index = {name: idx for idx, name in enumerate(names)}

    # Build package hash table and structured package map
    store, packages = build_packages_store(pack_rows, loc_index)

    # Simulate routes
    hub_id = 0
    trucks, total_miles = run_day(hub_id, M, packages)

    # Write back status/delivery times to the hash table (Task A/B consistency)
    for pid, p in packages.items():
        rec = ht_lookup_package(store, pid)
        if rec is None: continue
        rec['status'] = p.status
        rec['delivered_at'] = p.delivered_at
        ht_insert_package(store, pid, rec['address'], rec['deadline'], rec['city'], rec['zip'], rec['weight'], rec['status'], rec['delivered_at'])

    print(f"Total miles (all trucks): {total_miles:.2f}\n")
    while True:
        print("Choose an option:")
        print(" 1) Lookup package by ID at a time (HH:MM)")
        print(" 2) Show all package statuses at a time (HH:MM)")
        print(" 3) Show first 10 hash table buckets (screenshot aid)")
        print(" 4) Exit")
        choice = input("> ").strip()
        if choice == '1':
            pid = int(input("Enter Package ID: ").strip())
            timestr = input("Enter time (HH:MM): ").strip()
            at_time = datetime.combine(START_TIME.date(), datetime.strptime(timestr, '%H:%M').time())
            p = packages.get(pid)
            if not p:
                print("Not found.\n")
                continue
            # Use the Task B lookup result to print
            rec = ht_lookup_package(store, pid)
            status = 'HUB'
            delivered_at = ''
            if p.delivered_at and p.delivered_at <= at_time:
                status = 'DELIVERED'
                delivered_at = p.delivered_at.strftime('%H:%M')
            elif p.delivered_at and p.delivered_at > at_time:
                status = 'EN_ROUTE'
            print(f"\nPackage {pid}: {rec['address']}, {rec['city']} {rec['zip']}, deadline {rec['deadline']}, weight {rec['weight']:.1f}\nStatus at {timestr}: {status}, delivered_at={delivered_at}\n")
        elif choice == '2':
            timestr = input("Enter time (HH:MM): ").strip()
            at_time = datetime.combine(START_TIME.date(), datetime.strptime(timestr, '%H:%M').time())
            print_package_status(packages, at_time)
        elif choice == '3':
            buckets = store.first_n_buckets(10)
            print("\nFirst 10 buckets (for screenshot):\n")
            for idx, bucket in enumerate(buckets):
                print(f"Bucket {idx}: {bucket}")
            print()
        else:
            break
