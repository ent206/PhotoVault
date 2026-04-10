from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class TransferStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PhotoAsset:
    filename: str
    source_path: str
    date_taken: datetime
    file_size: int
    media_type: str  # "photo", "video", "live_photo_image", "live_photo_video"
    live_photo_pair_id: Optional[str] = None
    is_icloud_stub: bool = False


@dataclass
class FileRecord:
    filename: str
    source_path: str
    destination_path: str
    file_size: int
    status: TransferStatus = TransferStatus.PENDING
    checksum: Optional[str] = None
    transferred_at: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class TransferSession:
    session_id: str
    started_at: datetime
    source_device: str
    destination_path: str
    total_files: int
    files: List[FileRecord] = field(default_factory=list)

    def __post_init__(self):
        if self.files and self.total_files != len(self.files) and self.total_files > 0:
            # If files are provided at construction, total_files must match
            raise ValueError(
                f"total_files ({self.total_files}) != len(files) ({len(self.files)})"
            )

    @property
    def total_size_bytes(self) -> int:
        return sum(f.file_size for f in self.files)

    @property
    def completed_count(self) -> int:
        return sum(1 for f in self.files if f.status == TransferStatus.COMPLETED)

    @property
    def failed_files(self) -> List[FileRecord]:
        return [f for f in self.files if f.status == TransferStatus.FAILED]

    @property
    def is_complete(self) -> bool:
        if not self.files:
            return False
        return all(
            f.status in (TransferStatus.COMPLETED, TransferStatus.SKIPPED, TransferStatus.FAILED)
            for f in self.files
        )
