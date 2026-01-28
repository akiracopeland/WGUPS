# Models for packages and trucks (standard library only)
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime, time, timedelta

@dataclass
class Package:
    id: int
    address: str
    city: str
    zip: str
    deadline: str       # 'EOD' or 'HH:MM'
    weight: float
    note: str
    location_id: int    # numeric index in DistanceMatrix
    status: str = 'HUB' # 'HUB' | 'EN_ROUTE' | 'DELIVERED'
    delivered_at: Optional[datetime] = None

@dataclass
class Truck:
    id: int
    speed_mph: float
    capacity: int
    depart_time: datetime
    route: List[int]     # list of location_ids (hub first, then stops, then hub)
    carried: List[int]   # package IDs assigned to this wave
    return_time: Optional[datetime] = None
    miles: float = 0.0
