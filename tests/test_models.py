from datetime import datetime
from src.models import PhotoAsset, FileRecord, TransferSession, TransferStatus


def test_photo_asset_creation():
    asset = PhotoAsset(
        filename="IMG_0042.jpg",
        source_path="/DCIM/100APPLE/IMG_0042.jpg",
        date_taken=datetime(2024, 3, 15, 10, 30),
        file_size=3_500_000,
        media_type="photo",
        live_photo_pair_id=None,
        is_icloud_stub=False,
    )
    assert asset.filename == "IMG_0042.jpg"
    assert asset.file_size == 3_500_000


def test_file_record_defaults():
    record = FileRecord(
        filename="IMG_0042.jpg",
        source_path="/DCIM/100APPLE/IMG_0042.jpg",
        destination_path="/Volumes/Backup/2024/March/IMG_0042.jpg",
        file_size=3_500_000,
    )
    assert record.status == TransferStatus.PENDING
    assert record.checksum is None


def test_transfer_session_total_size():
    session = TransferSession(
        session_id="abc123",
        started_at=datetime(2024, 3, 15),
        source_device="iPhone 15 Pro",
        destination_path="/Volumes/Backup",
        total_files=2,
        files=[
            FileRecord("a.jpg", "/src/a.jpg", "/dst/a.jpg", 1000),
            FileRecord("b.jpg", "/src/b.jpg", "/dst/b.jpg", 2000),
        ]
    )
    assert session.total_size_bytes == 3000


def test_is_complete_empty_files():
    session = TransferSession(
        session_id="s1",
        started_at=datetime(2024, 1, 1),
        source_device="Mock",
        destination_path="/dst",
        total_files=0,
        files=[],
    )
    assert session.is_complete is False


def test_is_complete_with_all_statuses():
    session = TransferSession(
        session_id="s2",
        started_at=datetime(2024, 1, 1),
        source_device="Mock",
        destination_path="/dst",
        total_files=3,
        files=[
            FileRecord("a.jpg", "/s/a", "/d/a", 100, status=TransferStatus.COMPLETED),
            FileRecord("b.jpg", "/s/b", "/d/b", 100, status=TransferStatus.SKIPPED),
            FileRecord("c.jpg", "/s/c", "/d/c", 100, status=TransferStatus.FAILED),
        ]
    )
    assert session.is_complete is True
    assert session.completed_count == 1
    assert len(session.failed_files) == 1


def test_transfer_status_str_values():
    assert TransferStatus.PENDING == "pending"
    assert TransferStatus.COMPLETED == "completed"
