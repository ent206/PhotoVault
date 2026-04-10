from datetime import datetime
from pathlib import Path
import piexif
from PIL import Image
from src.device.mock_device import MockDevice


def _make_jpeg(path: Path, dt: datetime) -> None:
    img = Image.new("RGB", (10, 10))
    exif = piexif.dump({"Exif": {
        piexif.ExifIFD.DateTimeOriginal: dt.strftime("%Y:%m:%d %H:%M:%S").encode()
    }})
    img.save(str(path), format="JPEG", exif=exif)


def test_mock_device_connects(tmp_dir):
    dcim = tmp_dir / "DCIM" / "100APPLE"
    dcim.mkdir(parents=True)
    _make_jpeg(dcim / "IMG_1000.jpg", datetime(2024, 3, 15, 10, 0, 0))

    device = MockDevice(tmp_dir)
    device.connect()
    assert device.is_connected()
    info = device.device_info()
    assert "Mock iPhone" in info["model"]
    assert info["total_count"] >= 1


def test_mock_device_date_filter(tmp_dir):
    dcim = tmp_dir / "DCIM" / "100APPLE"
    dcim.mkdir(parents=True)
    _make_jpeg(dcim / "IMG_1000.jpg", datetime(2023, 6, 1, 10, 0, 0))
    _make_jpeg(dcim / "IMG_1001.jpg", datetime(2024, 6, 1, 10, 0, 0))

    device = MockDevice(tmp_dir)
    device.connect()
    assets = device.list_assets(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
    )
    assert len(assets) == 1
    assert assets[0].filename == "IMG_1001.jpg"


def test_mock_device_read_file(tmp_dir):
    dcim = tmp_dir / "DCIM" / "100APPLE"
    dcim.mkdir(parents=True)
    p = dcim / "IMG_9999.jpg"
    _make_jpeg(p, datetime(2024, 1, 1, 0, 0, 0))

    device = MockDevice(tmp_dir)
    device.connect()
    assets = device.list_assets(datetime(2024, 1, 1), datetime(2024, 12, 31))
    assert len(assets) == 1
    data = device.read_file(assets[0])
    assert len(data) > 0


def test_mock_device_live_photo_pair_detection(tmp_dir):
    dcim = tmp_dir / "DCIM" / "100APPLE"
    dcim.mkdir(parents=True)
    _make_jpeg(dcim / "IMG_2000.jpg", datetime(2024, 5, 1, 12, 0, 0))
    (dcim / "IMG_2000.mov").write_bytes(b"\x00" * 100)
    (dcim / "IMG_2000.photovault_meta").write_text("live_photo_pair_id=LP0001\n")

    device = MockDevice(tmp_dir)
    device.connect()
    assets = device.list_assets(datetime(2024, 1, 1), datetime(2024, 12, 31))
    # Should have 2 assets: live_photo_image and live_photo_video
    assert len(assets) == 2
    types = {a.media_type for a in assets}
    assert "live_photo_image" in types
    assert "live_photo_video" in types
    # Both should have the same pair_id
    pair_ids = {a.live_photo_pair_id for a in assets}
    assert pair_ids == {"LP0001"}


def test_mock_device_delete_file(tmp_dir):
    dcim = tmp_dir / "DCIM" / "100APPLE"
    dcim.mkdir(parents=True)
    p = dcim / "IMG_5000.jpg"
    _make_jpeg(p, datetime(2024, 3, 1, 9, 0, 0))

    device = MockDevice(tmp_dir)
    device.connect()
    assets = device.list_assets(datetime(2024, 1, 1), datetime(2024, 12, 31))
    assert len(assets) == 1
    device.delete_file(assets[0])
    assert not p.exists()
