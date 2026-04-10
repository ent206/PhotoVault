import struct
from datetime import datetime
from pathlib import Path

import piexif


def get_date_taken(path: Path) -> datetime:
    """Extract original capture date from a media file. Falls back to mtime."""
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        return _from_jpeg(path)
    if suffix == ".heic":
        return _from_heic(path)
    if suffix in (".mov", ".mp4", ".m4v"):
        return _from_quicktime(path)
    return _mtime(path)


def _from_jpeg(path: Path) -> datetime:
    try:
        exif = piexif.load(str(path))
        raw = exif.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
        if raw:
            return datetime.strptime(raw.decode(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return _mtime(path)


def _from_heic(path: Path) -> datetime:
    try:
        import pillow_heif
        heif = pillow_heif.read_heif(str(path))
        exif_data = heif.info.get("exif")
        if exif_data:
            exif = piexif.load(exif_data)
            raw = exif.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
            if raw:
                return datetime.strptime(raw.decode(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return _mtime(path)


def _from_quicktime(path: Path) -> datetime:
    """Parse QuickTime mvhd atom for creation time (seconds since 1904-01-01)."""
    EPOCH_OFFSET = 2082844800  # seconds between 1904-01-01 and 1970-01-01
    try:
        data = path.read_bytes()
        idx = 0
        while idx < len(data) - 8:
            box_size = struct.unpack(">I", data[idx:idx+4])[0]
            box_type = data[idx+4:idx+8]
            if box_type == b"mvhd" and box_size >= 24:
                version = data[idx+8]
                if version == 0:
                    ts = struct.unpack(">I", data[idx+12:idx+16])[0]
                else:
                    ts = struct.unpack(">Q", data[idx+12:idx+20])[0]
                unix_ts = ts - EPOCH_OFFSET
                if unix_ts > 0:
                    return datetime.fromtimestamp(unix_ts)
            if box_size < 8:
                break
            idx += box_size
    except Exception:
        pass
    return _mtime(path)


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)
