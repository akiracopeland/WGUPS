"""models.py

Dataclasses representing the core domain objects:

- Package: a deliverable item with an address, deadline, and delivery status.
- Truck: a delivery truck that carries packages and drives a computed route.

These are intentionally simple structures so the routing and simulation logic
lives in router.py and simulator.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class Package:
    """A package in the WGUPS system."""

    id: int
    address: str
    city: str
    zip: str
    deadline: str            # 'EOD' or a time string like '10:30' / '10:30 AM'
    weight: float
    note: str
    location_id: int         # numeric index in the distance matrix

    # Simulation fields (populated by simulator/router)
    status: str = 'HUB'      # 'HUB' | 'EN_ROUTE' | 'DELIVERED'
    depart_time: Optional[datetime] = None
    delivered_at: Optional[datetime] = None


@dataclass
class Truck:
    """A truck and the route it drives."""

    id: int
    speed_mph: float
    capacity: int
    depart_time: datetime

    # Route representation:
    # - route is a list of location_ids: [hub, stop1, stop2, ..., hub]
    route: List[int]

    # Package IDs assigned to this truck
    carried: List[int]

    # Populated by the router
    return_time: Optional[datetime] = None
    miles: float = 0.0
