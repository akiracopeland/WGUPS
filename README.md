# WGUPS Routing Program (Standard Library Only)

This project implements the C950 WGUPS routing simulation with a custom **HashTable** (no third‑party libraries).

## Files

- `main.py` — entry point (**first line must contain your WGU student ID**).
- `hash_table.py` — custom hash table with separate chaining + move‑to‑front.
- `models.py` — `Package` and `Truck` dataclasses.
- `data_loader.py` — CSV loaders for packages and distance matrix.
- `router.py` — nearest‑neighbor + bounded 2‑opt route builder.
- `simulator.py` — assigns trucks, applies time-gated constraints (e.g., package #9 @ 10:20), runs routes.
- `cli.py` — interactive command‑line tool for lookups and snapshots.
- `data/` — place `packages.csv` and `distances.csv` here.

## Data Preparation

**Do not** require any third‑party library at runtime. Convert your Excel files to CSV **once** and place them under `data/`:

- `data/packages.csv` with columns:
  `ID,Address,City,Zip,Deadline,Weight,Note`

- `data/distances.csv` — the WGUPS table copied to CSV. Keep the first row and first column as location names; lower‑triangular distances are fine (the loader mirrors them). Ensure the **first name** is the **hub**.

## Run

From the `wgups_project/` folder:

```bash
python3 main.py
```

Then use the menu to:
- Lookup any package by ID at a time.
- Print status for **all** packages at a time (for screenshots at the requested windows).
- Show first 10 buckets of the custom hash table (for your A/B screenshots).
- Show the completion report with the total mileage for each truck.

## Notes

- Speed is fixed at 18 mph.
- Capacity is 16 per truck.
- Package #9 has a corrected address at **10:20**; time‑gated packages are respected.
- The algorithm is **nearest‑neighbor with a small 2‑opt pass**, which is polynomial time and adapts mid‑day.
