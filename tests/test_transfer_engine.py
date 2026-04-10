import hashlib
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import piexif
from PIL import Image

from src.device.mock_device import MockDevice
from src.models import TransferStatus
from src.session_log import SessionLog
from src.transfer_engine import TransferEngine, TransferOptions


def _make_mock_library(tmp_dir: Path) -> Path:
    """Creates a small mock DCIM for engine tests."""
    dcim = tmp_dir / "mock" / "DCIM" / "100APPLE"
    dcim.mkdir(parents=True)
    for i in range(2):
        img = Image.new("RGB", (50, 50), color=(i * 60, 100, 200))
        exif = piexif.dump({"Exif": {
            piexif.ExifIFD.DateTimeOriginal: f"2024:0{i+1}:15 12:00:00".encode()
        }})
        p = dcim / f"IMG_{1000+i}.jpg"
        img.save(str(p), format="JPEG", exif=exif)
    return tmp_dir / "mock"


def test_transfer_completes_all_files(tmp_dir):
    mock_root = _make_mock_library(tmp_dir)
    dest = tmp_dir / "dest"
    dest.mkdir()
    log = SessionLog(tmp_dir / "logs")
    device = MockDevice(mock_root)
    device.connect()

    options = TransferOptions(safe_mode=True, session_id="test-engine-01")
    engine = TransferEngine(device, dest, log, options)
    assets = device.list_assets(datetime(2024, 1, 1), datetime(2024, 12, 31))
    results = engine.transfer(assets)

    assert results["completed"] == 2
    assert results["failed"] == 0
    copied = list(dest.rglob("*.jpg"))
    assert len(copied) == 2


def test_duplicate_files_are_skipped(tmp_dir):
    mock_root = _make_mock_library(tmp_dir)
    dest = tmp_dir / "dest"
    dest.mkdir()
    log = SessionLog(tmp_dir / "logs")
    device = MockDevice(mock_root)
    device.connect()
    assets = device.list_assets(datetime(2024, 1, 1), datetime(2024, 12, 31))

    # First transfer
    opts1 = TransferOptions(safe_mode=False, session_id="run-01")
    TransferEngine(device, dest, log, opts1).transfer(assets)

    # Second transfer with same assets
    opts2 = TransferOptions(safe_mode=False, session_id="run-02")
    results = TransferEngine(device, dest, log, opts2).transfer(assets)
    assert results["skipped"] == 2
    assert results["completed"] == 0


def test_no_partial_files_on_failure(tmp_dir):
    mock_root = _make_mock_library(tmp_dir)
    dest = tmp_dir / "dest"
    dest.mkdir()
    log = SessionLog(tmp_dir / "logs")
    device = MockDevice(mock_root)
    device.connect()
    assets = device.list_assets(datetime(2024, 1, 1), datetime(2024, 12, 31))

    with patch.object(device, "read_file", side_effect=IOError("device disconnected")):
        opts = TransferOptions(safe_mode=False, session_id="fail-01")
        results = TransferEngine(device, dest, log, opts).transfer(assets)

    assert results["failed"] == 2
    partials = list(dest.rglob("*.photovault_partial"))
    assert len(partials) == 0


def test_session_log_written_correctly(tmp_dir):
    mock_root = _make_mock_library(tmp_dir)
    dest = tmp_dir / "dest"
    dest.mkdir()
    log = SessionLog(tmp_dir / "logs")
    device = MockDevice(mock_root)
    device.connect()
    assets = device.list_assets(datetime(2024, 1, 1), datetime(2024, 12, 31))

    opts = TransferOptions(safe_mode=True, session_id="log-test-01")
    TransferEngine(device, dest, log, opts).transfer(assets)

    session = log.load("log-test-01")
    assert all(f.status == TransferStatus.COMPLETED for f in session.files)
    assert all(f.checksum is not None for f in session.files)


def test_cleanup_partials(tmp_dir):
    # Create some fake partial files
    (tmp_dir / "photo.jpg.photovault_partial").write_bytes(b"garbage")
    (tmp_dir / "subdir").mkdir()
    (tmp_dir / "subdir" / "vid.mov.photovault_partial").write_bytes(b"garbage")

    from src.transfer_engine import TransferEngine
    count = TransferEngine.cleanup_partials(tmp_dir)
    assert count == 2
    assert not list(tmp_dir.rglob("*.photovault_partial"))
