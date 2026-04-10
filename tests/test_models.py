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
