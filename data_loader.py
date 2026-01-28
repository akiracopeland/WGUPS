# Data loading utilities (CSV only). No third-party libraries.
import csv
from typing import Dict, List, Tuple
from models import Package

def load_packages_csv(path: str) -> List[dict]:
    rows = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            # Normalize keys we rely on
            rows.append({
                'ID': int(str(row.get('ID') or row.get('PackageID') or row.get('Package') or '0')),
                'Address': (row.get('Address') or row.get('Delivery Address') or '').strip(),
                'City': (row.get('City') or '').strip(),
                'Zip': str(row.get('Zip') or row.get('Zip Code') or '').strip(),
                'Deadline': (row.get('Deadline') or row.get('Delivery Deadline') or 'EOD').strip(),
                'Weight': float(str(row.get('Weight') or '0').strip() or 0),
                'Note': (row.get('Note') or row.get('Special Note') or '').strip()
            })
    return rows

def load_distance_matrix_csv(path: str) -> Tuple[List[str], List[List[float]]]:
    # Expect a square matrix CSV with names in first row and first column (WGUPS format is flexible).
    # We'll make a best effort parser that reads everything and mirrors the lower triangle.
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    # heuristic: first row has names in columns 1..N
    # first column (rows[1..]) has names in col 0
    # distances at [i][j] for i>=j or j>=i
    # Clean names
    names = []
    # Get column headers from row 0 (skip col 0 if blank or label)
    header = rows[0]
    # Some tables have empty top-left then names across; others have name repeated in col0
    for j in range(len(header)):
        if j == 0:
            # top-left often empty or 'Hub'
            continue
        names.append(header[j].strip())
    # If header names are empty, try first column instead
    if not any(names):
        names = []
        for i in range(1, len(rows)):
            names.append((rows[i][0] or '').strip())

    N = len(names)
    # Initialize matrix
    M = [[0.0 for _ in range(N)] for _ in range(N)]
    # Fill from cells; attempt to parse floats; if blank, mirror the symmetric value later
    for i in range(1, len(rows)):
        for j in range(1, len(rows[i])):
            si = i-1
            sj = j-1
            if si < N and sj < N:
                cell = (rows[i][j] or '').strip()
                if cell:
                    try:
                        M[si][sj] = float(cell)
                    except:
                        pass
    # Mirror symmetric distances
    for i in range(N):
        for j in range(N):
            if i == j:
                M[i][j] = 0.0
            else:
                if M[i][j] == 0.0 and M[j][i] != 0.0:
                    M[i][j] = M[j][i]
                elif M[j][i] == 0.0 and M[i][j] != 0.0:
                    M[j][i] = M[i][j]
    # Fallback: if still zero in both directions and names look valid, estimate via triangle inequality is NOT required; leave 0 -> later logic can skip, but WGUPS tables are fully connected.
    return names, M

def build_location_index(names: List[str]) -> Dict[str, int]:
    # Map address names to numeric indices. We use the raw names as keys.
    # Caller should normalize strings to match table names.
    return {names[i]: i for i in range(len(names))}
