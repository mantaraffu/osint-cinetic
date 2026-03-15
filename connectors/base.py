from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class NormalizedEvent:
    timestamp: str
    location_name: str
    lat: float
    lng: float
    event_type: str
    description: str
    source: str
    source_url: str
    raw: Optional[dict] = None


class OsintConnector(ABC):

    id: str
    name: str
    frequency_minutes: int

    @abstractmethod
    def fetch_latest(self) -> Optional[NormalizedEvent]:
        ...
