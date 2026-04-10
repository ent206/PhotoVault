# src/device/iphone_device.py
"""
Real iPhone device implementation using pymobiledevice3.

Requires:
- iPhone connected via USB and trusted
- For iOS 17+: tunnel service running (started from Screen 1 or manually)
  sudo python3 -m pymobiledevice3 remote start-quic-tunnel
"""
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.device.base import DeviceInterface
from src.models import PhotoAsset

MEDIA_EXTS = {".jpg", ".jpeg", ".heic", ".mov", ".mp4", ".m4v"}
LIVE_PHOTO_VIDEO_EXTS = {".mov"}


class iPhoneDevice(DeviceInterface):
    def __init__(self):
        self._lockdown = None
        self._afc = None
        self._assets: Optional[List[PhotoAsset]] = None
        self._info: Optional[Dict] = None

    def connect(self) -> None:
        try:
            from pymobiledevice3.lockdown import create_using_usbmux
            from pymobiledevice3.services.afc import AfcClient
            self._lockdown = create_using_usbmux()
            self._afc = AfcClient(lockdown=self._lockdown)
        except Exception as e:
            # Check if it's an iOS 17+ tunnel error
            err = str(e).lower()
            if "tunnel" in err or "quic" in err or "remotepairing" in err:
                from src.gui.screen1_connect import NeedsTunnelError
                raise NeedsTunnelError(str(e)) from e
            raise ConnectionError(f"Could not connect to iPhone: {e}") from e

        self._info = self._fetch_device_info()
        self._assets = self._scan_dcim()

    def is_connected(self) -> bool:
        return self._lockdown is not None

    def disconnect(self) -> None:
        self._lockdown = None
        self._afc = None

    def device_info(self) -> Dict:
        return self._info

    def list_assets(self, start_date: datetime, end_date: datetime) -> List[PhotoAsset]:
        return [a for a in self._assets if start_date <= a.date_taken <= end_date]

    def read_file(self, asset: PhotoAsset) -> bytes:
        try:
            return self._afc.get_file_contents(asset.source_path)
        except Exception as e:
            raise IOError(f"Failed to read {asset.source_path} from device: {e}") from e

    def delete_file(self, asset: PhotoAsset) -> None:
        try:
            self._afc.rm(asset.source_path)
        except Exception as e:
            raise IOError(f"Failed to delete {asset.source_path} from device: {e}") from e

    def _fetch_device_info(self) -> Dict:
        try:
            ios_version = self._lockdown.product_version
        except Exception:
            ios_version = "Unknown"

        try:
            model = self._lockdown.product_type  # e.g. "iPhone15,2"
        except Exception:
            model = "iPhone"

        # Count media files in DCIM
        total = self._count_dcim_files()

        return {
            "model": model,
            "ios_version": ios_version,
            "total_count": total,
            "total_size_bytes": 0,  # Computing size requires stat on each file — skip for perf
        }

    def _count_dcim_files(self) -> int:
        count = 0
        try:
            for folder in self._afc.listdir("/DCIM"):
                if folder.startswith("."):
                    continue
                try:
                    for fname in self._afc.listdir(f"/DCIM/{folder}"):
                        if Path(fname).suffix.lower() in MEDIA_EXTS:
                            count += 1
                except Exception:
                    pass
        except Exception:
            pass
        return count

    def _scan_dcim(self) -> List[PhotoAsset]:
        from src.utils.exif_utils import get_date_taken

        all_files: Dict[str, List[tuple]] = {}  # stem -> [(fname, folder_path, ext)]

        try:
            for folder in self._afc.listdir("/DCIM"):
                if folder.startswith("."):
                    continue
                folder_path = f"/DCIM/{folder}"
                try:
                    for fname in self._afc.listdir(folder_path):
                        ext = Path(fname).suffix.lower()
                        if ext not in MEDIA_EXTS:
                            continue
                        stem = Path(fname).stem
                        all_files.setdefault(stem, []).append((fname, folder_path, ext))
                except Exception:
                    pass
        except Exception:
            return []

        # Identify Live Photo pairs: same stem has both image ext and .mov
        pair_ids: Dict[str, str] = {}
        for stem, entries in all_files.items():
            exts = {e for _, _, e in entries}
            has_image = bool(exts & {".jpg", ".jpeg", ".heic"})
            has_mov = ".mov" in exts
            if has_image and has_mov:
                pair_ids[stem] = f"LP_{stem}"

        assets = []
        with tempfile.TemporaryDirectory() as tmpdir:
            # First pass: collect image dates for Live Photo stems
            image_dates: Dict[str, datetime] = {}
            for stem, entries in all_files.items():
                if stem not in pair_ids:
                    continue
                for fname, folder_path, ext in entries:
                    if ext in {".jpg", ".jpeg", ".heic"}:
                        try:
                            # Sample first 256KB to get EXIF without pulling full file
                            sample = self._afc.get_file_contents(
                                f"{folder_path}/{fname}"
                            )[:262144]
                            tmp = Path(tmpdir) / fname
                            tmp.write_bytes(sample)
                            image_dates[stem] = get_date_taken(tmp)
                        except Exception:
                            pass

            # Second pass: build all assets
            for stem, entries in all_files.items():
                for fname, folder_path, ext in entries:
                    full_path = f"{folder_path}/{fname}"
                    pair_id = pair_ids.get(stem)

                    if pair_id and ext in LIVE_PHOTO_VIDEO_EXTS:
                        media_type = "live_photo_video"
                    elif pair_id:
                        media_type = "live_photo_image"
                    elif ext in {".mov", ".mp4", ".m4v"}:
                        media_type = "video"
                    else:
                        media_type = "photo"

                    # Get date: use paired image date for live photo videos
                    date_taken = datetime.now()
                    if pair_id and ext in LIVE_PHOTO_VIDEO_EXTS and stem in image_dates:
                        date_taken = image_dates[stem]
                    else:
                        try:
                            sample = self._afc.get_file_contents(full_path)[:262144]
                            tmp = Path(tmpdir) / fname
                            tmp.write_bytes(sample)
                            date_taken = get_date_taken(tmp)
                        except Exception:
                            pass

                    # File size via stat
                    file_size = 0
                    try:
                        stat = self._afc.stat(full_path)
                        file_size = int(stat.get("st_size", 0))
                    except Exception:
                        pass

                    # iCloud stub heuristic: photo file < 50KB is likely a placeholder
                    is_stub = (
                        media_type in ("photo", "live_photo_image")
                        and file_size > 0
                        and file_size < 51200
                    )

                    assets.append(PhotoAsset(
                        filename=fname,
                        source_path=full_path,
                        date_taken=date_taken,
                        file_size=file_size,
                        media_type=media_type,
                        live_photo_pair_id=pair_id,
                        is_icloud_stub=is_stub,
                    ))
        return assets
