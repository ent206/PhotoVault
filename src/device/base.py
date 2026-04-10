from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List
from src.models import PhotoAsset


class DeviceInterface(ABC):

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to device. Raises ConnectionError on failure."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if device is currently connected."""

    @abstractmethod
    def disconnect(self) -> None:
        """Cleanly disconnect."""

    @abstractmethod
    def device_info(self) -> Dict:
        """Return dict with keys: model, ios_version, total_count, total_size_bytes."""

    @abstractmethod
    def list_assets(self, start_date: datetime, end_date: datetime) -> List[PhotoAsset]:
        """Return all assets with date_taken in [start_date, end_date] inclusive."""

    @abstractmethod
    def read_file(self, asset: PhotoAsset) -> bytes:
        """Read and return file bytes from the device."""

    @abstractmethod
    def delete_file(self, asset: PhotoAsset) -> None:
        """Permanently delete a file from the device."""
