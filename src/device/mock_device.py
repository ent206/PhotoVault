from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.device.base import DeviceInterface
from src.models import PhotoAsset
from src.utils.exif_utils import get_date_taken

MEDIA_EXTS = {".jpg", ".jpeg", ".heic", ".mov", ".mp4", ".m4v"}
LIVE_PHOTO_VIDEO_EXTS = {".mov"}


class MockDevice(DeviceInterface):
    def __init__(self, mock_root: Path):
        self._root = Path(mock_root)
        self._connected = False
        self._assets: Optional[List[PhotoAsset]] = None

    def connect(self) -> None:
        if not (self._root / "DCIM").exists():
            raise ConnectionError(f"No DCIM folder found in {self._root}")
        self._connected = True
        self._assets = self._scan()

    def is_connected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        self._connected = False

    def device_info(self) -> Dict:
        assert self._connected, "Not connected"
        return {
            "model": "Mock iPhone 15 Pro",
            "ios_version": "17.4",
            "total_count": len(self._assets),
            "total_size_bytes": sum(a.file_size for a in self._assets),
        }

    def list_assets(self, start_date: datetime, end_date: datetime) -> List[PhotoAsset]:
        assert self._connected, "Not connected"
        return [
            a for a in self._assets
            if start_date <= a.date_taken <= end_date
        ]

    def read_file(self, asset: PhotoAsset) -> bytes:
        assert self._connected, "Not connected"
        return Path(asset.source_path).read_bytes()

    def delete_file(self, asset: PhotoAsset) -> None:
        assert self._connected, "Not connected"
        Path(asset.source_path).unlink(missing_ok=True)

    def _scan(self) -> List[PhotoAsset]:
        """Scan DCIM folder and build asset list, detecting Live Photo pairs via sidecars."""
        # Load pair IDs from .photovault_meta sidecar files
        pair_ids: Dict[str, str] = {}
        for sidecar in self._root.rglob("*.photovault_meta"):
            stem = sidecar.stem
            for line in sidecar.read_text().splitlines():
                if line.startswith("live_photo_pair_id="):
                    pair_ids[stem] = line.split("=", 1)[1].strip()

        # First pass: collect dates for image stems (so live photo videos can inherit them)
        stem_dates: Dict[str, datetime] = {}
        for f in self._root.rglob("*"):
            if not f.is_file():
                continue
            suffix = f.suffix.lower()
            if suffix in MEDIA_EXTS and suffix not in LIVE_PHOTO_VIDEO_EXTS:
                try:
                    stem_dates[f.stem] = get_date_taken(f)
                except Exception:
                    pass

        assets = []
        for f in self._root.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in MEDIA_EXTS:
                continue

            suffix = f.suffix.lower()
            stem = f.stem
            pair_id = pair_ids.get(stem)

            if pair_id and suffix in LIVE_PHOTO_VIDEO_EXTS:
                media_type = "live_photo_video"
            elif pair_id:
                media_type = "live_photo_image"
            elif suffix in {".mov", ".mp4", ".m4v"}:
                media_type = "video"
            else:
                media_type = "photo"

            # For live photo videos, inherit the paired image's date if available
            if media_type == "live_photo_video" and stem in stem_dates:
                date_taken = stem_dates[stem]
            else:
                try:
                    date_taken = get_date_taken(f)
                except Exception:
                    date_taken = datetime(2000, 1, 1)

            assets.append(PhotoAsset(
                filename=f.name,
                source_path=str(f),
                date_taken=date_taken,
                file_size=f.stat().st_size,
                media_type=media_type,
                live_photo_pair_id=pair_id,
                is_icloud_stub=False,
            ))
        return assets
