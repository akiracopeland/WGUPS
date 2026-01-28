"""data_loader.py

CSV loaders for:
- packages.csv
- distances.csv (WGUPS distance table exported to CSV)

Important: The distance table is commonly exported from Excel and may contain:
- leading metadata rows
- merged cells
- blank columns/rows
- lower-triangular-only distances

This loader makes a best-effort attempt to find the real square table inside the CSV,
then produces:
- a list of location names (index 0 is the HUB)
- a symmetric NxN float distance matrix
"""

from __future__ import annotations

import csv
from typing import List, Tuple, Optional


def load_packages_csv(path: str) -> List[dict]:
    """Load packages from a CSV into a list of normalized dict rows."""
    rows: List[dict] = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            # Normalize the keys we rely on (allows minor header variations).
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


def _to_float(cell: str) -> Optional[float]:
    """Try to parse a float from a CSV cell; return None if not parseable."""
    if cell is None:
        return None
    s = str(cell).strip()
    if not s:
        return None
    # Some exports include stray quotes or spaces.
    s = s.replace('"', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


def _score_header_row(row: List[str]) -> int:
    """Heuristic score: how likely is this row the header row of location names?"""
    # We want many non-empty, non-numeric cells after col 0.
    score = 0
    for cell in row[1:]:
        s = (cell or '').strip()
        if not s:
            continue
        if _to_float(s) is None:
            score += 1
    return score


def load_distance_matrix_csv(path: str) -> Tuple[List[str], List[List[float]]]:
    """Load a WGUPS distance table CSV into (names, matrix).

    The most common “clean” shape is:
        header row: ['', name0, name1, ...]
        each following row: [row_name, d0, d1, ...]

    But the messy export can include multiple blank/metadata rows above the table.
    We therefore:
      1) scan for the best header row candidate
      2) read the next N rows as the table body
      3) parse floats where possible
      4) mirror the lower/upper triangle to make a symmetric matrix
    """
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))

    if not rows:
        raise ValueError('Distance CSV is empty.')

    # 1) Find the row that looks most like a header row of location names.
    best_i = None
    best_score = -1
    for i, row in enumerate(rows):
        if len(row) < 4:
            continue
        score = _score_header_row(row)
        # Require a minimum density to avoid picking random metadata rows.
        if score > best_score and score >= 5:
            best_score = score
            best_i = i

    if best_i is None:
        raise ValueError('Could not locate a distance-table header row in the CSV.')

    header = rows[best_i]
    names = [c.strip() for c in header[1:] if (c or '').strip()]

    # 2) Read the body rows following the header. The body should have N rows with a non-empty name in col 0.
    body: List[List[str]] = []
    j = best_i + 1
    while j < len(rows) and len(body) < len(names):
        row = rows[j]
        if row and (row[0] or '').strip():
            body.append(row)
        j += 1

    # Some exports repeat names in col 0 and also include a full header row with commas.
    # If we didn't collect enough body rows, try a second strategy: search for consecutive rows with names.
    if len(body) < len(names):
        body = []
        for k in range(best_i + 1, len(rows)):
            row = rows[k]
            if row and (row[0] or '').strip():
                body.append(row)
                if len(body) == len(names):
                    break

    n = len(names)
    if len(body) < n:
        raise ValueError(f'Found header with {n} locations but only {len(body)} data rows.')

    # Clean name strings (Excel exports sometimes contain embedded newlines).
    names = [' '.join(name.replace('\n', ' ').replace('\r', ' ').split()) for name in names]

    # 3) Parse distances into an NxN matrix.
    M: List[List[float]] = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        row = body[i]        # Distances are usually in columns 1..N, but messy Excel exports sometimes insert
        # an extra "label" column, shifting the numeric cells right (e.g., a 'HUB' column).
        # We detect the first numeric cell and treat it as the start of the distance row.
        start_col = None
        for k in range(1, len(row)):
            if _to_float(row[k]) is not None:
                start_col = k
                break
        if start_col is None:
            continue

        for j in range(n):
            col = start_col + j
            if col >= len(row):
                break
            val = _to_float(row[col])
            if val is not None:
                M[i][j] = val

    # 4) Mirror triangle and ensure diagonal is 0.
    for i in range(n):
        M[i][i] = 0.0
        for j in range(n):
            if i == j:
                continue
            if M[i][j] == 0.0 and M[j][i] != 0.0:
                M[i][j] = M[j][i]
            elif M[j][i] == 0.0 and M[i][j] != 0.0:
                M[j][i] = M[i][j]

    return names, M
