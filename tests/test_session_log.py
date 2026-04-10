from datetime import datetime
from pathlib import Path
from src.session_log import SessionLog
from src.models import FileRecord, TransferSession, TransferStatus


def test_create_and_load(tmp_dir):
    log = SessionLog(log_dir=tmp_dir)
    session = TransferSession(
        session_id="test-001",
        started_at=datetime(2024, 3, 15, 10, 0),
        source_device="Mock iPhone",
        destination_path="/Volumes/Backup",
        total_files=2,
        files=[
            FileRecord("a.jpg", "/src/a.jpg", "/dst/a.jpg", 1000),
            FileRecord("b.jpg", "/src/b.jpg", "/dst/b.jpg", 2000),
        ]
    )
    log.save(session)
    loaded = log.load("test-001")
    assert loaded.session_id == "test-001"
    assert len(loaded.files) == 2
    assert loaded.files[0].status == TransferStatus.PENDING


def test_update_file_status(tmp_dir):
    log = SessionLog(log_dir=tmp_dir)
    session = TransferSession(
        session_id="test-002",
        started_at=datetime(2024, 3, 15),
        source_device="Mock",
        destination_path="/dst",
        total_files=1,
        files=[FileRecord("a.jpg", "/src/a.jpg", "/dst/a.jpg", 500)],
    )
    log.save(session)
    log.update_file(session.session_id, "a.jpg", TransferStatus.COMPLETED, checksum="abc123")
    loaded = log.load("test-002")
    assert loaded.files[0].status == TransferStatus.COMPLETED
    assert loaded.files[0].checksum == "abc123"


def test_find_incomplete(tmp_dir):
    log = SessionLog(log_dir=tmp_dir)
    s1 = TransferSession("s1", datetime(2024, 1, 1), "dev", "/dst", 1,
                         [FileRecord("a.jpg", "/s/a", "/d/a", 100)])
    s2 = TransferSession("s2", datetime(2024, 1, 2), "dev", "/dst", 1,
                         [FileRecord("b.jpg", "/s/b", "/d/b", 100,
                                     status=TransferStatus.COMPLETED)])
    log.save(s1)
    log.save(s2)
    incomplete = log.find_incomplete()
    assert len(incomplete) == 1
    assert incomplete[0].session_id == "s1"


def test_session_roundtrip_preserves_checksum(tmp_dir):
    log = SessionLog(log_dir=tmp_dir)
    session = TransferSession(
        session_id="test-003",
        started_at=datetime(2024, 6, 1, 8, 0),
        source_device="iPhone",
        destination_path="/Volumes/X",
        total_files=1,
        files=[FileRecord("photo.jpg", "/src/photo.jpg", "/dst/photo.jpg", 3000,
                           status=TransferStatus.COMPLETED, checksum="deadbeef")],
    )
    log.save(session)
    loaded = log.load("test-003")
    assert loaded.files[0].checksum == "deadbeef"
    assert loaded.files[0].status == TransferStatus.COMPLETED
