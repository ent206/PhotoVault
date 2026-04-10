import struct
from datetime import datetime
from pathlib import Path
import piexif
from PIL import Image
from src.utils.exif_utils import get_date_taken

def _make_jpeg_with_exif(path: Path, dt: datetime) -> None:
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    exif_bytes = piexif.dump({
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: dt.strftime("%Y:%m:%d %H:%M:%S").encode()
        }
    })
    img.save(str(path), format="JPEG", exif=exif_bytes)

def test_jpeg_exif_date(tmp_dir):
    target = datetime(2023, 11, 5, 14, 22, 0)
    p = tmp_dir / "photo.jpg"
    _make_jpeg_with_exif(p, target)
    result = get_date_taken(p)
    assert result == target

def test_fallback_to_mtime(tmp_dir):
    p = tmp_dir / "video.mov"
    p.write_bytes(b"\x00" * 100)
    result = get_date_taken(p)
    assert isinstance(result, datetime)

def test_unknown_extension_fallback(tmp_dir):
    p = tmp_dir / "file.xyz"
    p.write_bytes(b"\x00" * 10)
    result = get_date_taken(p)
    assert isinstance(result, datetime)
