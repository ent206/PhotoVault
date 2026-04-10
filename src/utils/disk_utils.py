# src/utils/disk_utils.py
import shutil
from pathlib import Path
from typing import List, NamedTuple


class DriveInfo(NamedTuple):
    name: str         # Display name (e.g. "Backup Drive")
    path: Path        # Mount point
    total_bytes: int
    free_bytes: int
    is_external: bool


def list_drives() -> List[DriveInfo]:
    """Return all mounted drives visible in /Volumes."""
    drives = []
    volumes = Path("/Volumes")
    if not volumes.exists():
        return drives
    for vol in volumes.iterdir():
        if not vol.is_dir():
            continue
        try:
            usage = shutil.disk_usage(vol)
            is_ext = vol.name != "Macintosh HD"
            drives.append(DriveInfo(
                name=vol.name,
                path=vol,
                total_bytes=usage.total,
                free_bytes=usage.free,
                is_external=is_ext,
            ))
        except (PermissionError, OSError):
            continue
    return sorted(drives, key=lambda d: (not d.is_external, d.name))


def check_space(destination: Path, required_bytes: int) -> dict:
    """
    Check if destination has enough space.
    Returns: {'ok': bool, 'free': int, 'headroom_pct': float}
    headroom_pct is the percentage of free space remaining AFTER the transfer.
    """
    try:
        usage = shutil.disk_usage(destination)
        free = usage.free
    except OSError:
        return {"ok": False, "free": 0, "headroom_pct": 0.0}

    if required_bytes == 0:
        return {"ok": True, "free": free, "headroom_pct": 100.0}

    headroom_pct = ((free - required_bytes) / free * 100) if free > 0 else 0.0
    return {
        "ok": free > required_bytes,
        "free": free,
        "headroom_pct": headroom_pct,
    }


def human_size(num_bytes: int) -> str:
    """Format bytes as human-readable string (e.g. '4.2 GB')."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"
