#!/usr/bin/env python3
"""
Creates a realistic mock iPhone DCIM library for PhotoVault testing.
Usage: python create_mock_library.py [--output ./mock_library]
"""
import argparse
import random
import shutil
import struct
from datetime import datetime, timedelta
from pathlib import Path

import piexif
from PIL import Image

SEED = 42
random.seed(SEED)

START_DATE = datetime(2022, 1, 1)
END_DATE = datetime(2024, 12, 31)
# Some files outside the typical test window (before 2022)
OUTSIDE_DATES = [datetime(2021, 6, 15), datetime(2020, 12, 1)]

PHOTO_SIZES = [
    (2_800_000, 4_500_000),   # typical HEIC ~3-4MB
    (1_500_000, 3_000_000),   # compressed JPEG
]
VIDEO_SIZES = [
    (10_000_000, 80_000_000),  # short clips
    (80_000_000, 300_000_000), # longer videos
]


def random_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def make_jpeg(path: Path, dt: datetime, size_bytes: int, color: tuple) -> None:
    img = Image.new("RGB", (800, 600), color=color)
    exif_bytes = piexif.dump({
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: dt.strftime("%Y:%m:%d %H:%M:%S").encode(),
            piexif.ExifIFD.DateTimeDigitized: dt.strftime("%Y:%m:%d %H:%M:%S").encode(),
        },
        "0th": {
            piexif.ImageIFD.Make: b"Apple",
            piexif.ImageIFD.Model: b"iPhone 15 Pro",
        }
    })
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif_bytes, quality=85)
    img_bytes = buf.getvalue()
    pad = max(0, size_bytes - len(img_bytes))
    path.write_bytes(img_bytes + b"\x00" * pad)


def make_heic(path: Path, dt: datetime, size_bytes: int) -> None:
    """Create a HEIC stub — a renamed JPEG for mock purposes."""
    tmp = path.with_suffix(".jpg_tmp")
    make_jpeg(tmp, dt, size_bytes, (0, 128, 255))
    tmp.rename(path)


def make_mov(path: Path, dt: datetime, size_bytes: int) -> None:
    """Create a minimal QuickTime .mov with embedded creation date."""
    EPOCH_OFFSET = 2082844800
    qt_ts = int(dt.timestamp()) + EPOCH_OFFSET
    # Build a minimal valid QuickTime file
    # mvhd box (version 0)
    creation_time = struct.pack(">I", qt_ts)
    modification_time = struct.pack(">I", qt_ts)
    # mvhd: 4 size + 4 type + 1 version + 3 flags + 4 create + 4 modify + 4 timescale + 4 duration + ...
    mvhd_content = (
        b"\x00" +          # version 0
        b"\x00\x00\x00" +  # flags
        creation_time +
        modification_time +
        b"\x00\x00\x02\x58" +  # timescale = 600
        b"\x00\x00\x00\x00" +  # duration = 0
        b"\x00\x01\x00\x00" +  # preferred rate
        b"\x01\x00" +          # preferred volume
        b"\x00" * 70           # padding to make valid mvhd
    )
    mvhd_size = 8 + len(mvhd_content)
    mvhd_box = struct.pack(">I", mvhd_size) + b"mvhd" + mvhd_content

    moov_size = 8 + len(mvhd_box)
    moov_box = struct.pack(">I", moov_size) + b"moov" + mvhd_box

    ftyp_box = struct.pack(">I", 20) + b"ftyp" + b"qt  " + b"\x00\x00\x00\x00" + b"qt  "

    header = ftyp_box + moov_box
    pad = max(0, size_bytes - len(header))
    path.write_bytes(header + b"\x00" * pad)


def make_mp4(path: Path, dt: datetime, size_bytes: int) -> None:
    make_mov(path, dt, size_bytes)


def generate(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    dcim = output_dir / "DCIM" / "100APPLE"
    dcim.mkdir(parents=True)

    counter = 1000
    files_created = 0

    def next_num():
        nonlocal counter
        n = counter
        counter += 1
        return n

    # 20 Live Photo pairs (JPEG + MOV same stem, same timestamp)
    print("Creating 20 Live Photo pairs...")
    for i in range(20):
        n = next_num()
        dt = random_date(START_DATE, END_DATE)
        size_img = random.randint(*PHOTO_SIZES[0])
        size_vid = random.randint(1_000_000, 5_000_000)
        pair_id = f"LP{i:04d}"
        img_path = dcim / f"IMG_{n:04d}.jpg"
        mov_path = dcim / f"IMG_{n:04d}.mov"
        make_jpeg(img_path, dt, size_img, (random.randint(0,255), random.randint(0,255), random.randint(0,255)))
        make_mov(mov_path, dt, size_vid)
        # Sidecar for mock device to identify the pair
        sidecar = dcim / f"IMG_{n:04d}.photovault_meta"
        sidecar.write_text(f"live_photo_pair_id={pair_id}\n")
        files_created += 2

    # Regular JPEGs (~200)
    print("Creating ~200 regular JPEGs...")
    for _ in range(200):
        n = next_num()
        dt = random_date(START_DATE, END_DATE)
        size = random.randint(*random.choice(PHOTO_SIZES))
        make_jpeg(dcim / f"IMG_{n:04d}.jpg", dt, size,
                  (random.randint(0,255), random.randint(0,255), random.randint(0,255)))
        files_created += 1

    # HEIC files (~150)
    print("Creating ~150 HEIC files...")
    for _ in range(150):
        n = next_num()
        dt = random_date(START_DATE, END_DATE)
        size = random.randint(*PHOTO_SIZES[0])
        make_heic(dcim / f"IMG_{n:04d}.heic", dt, size)
        files_created += 1

    # MOV videos (~60)
    print("Creating ~60 MOV videos...")
    for _ in range(60):
        n = next_num()
        dt = random_date(START_DATE, END_DATE)
        size = random.randint(10_000_000, 50_000_000)
        make_mov(dcim / f"IMG_{n:04d}.mov", dt, size)
        files_created += 1

    # MP4 videos (~30)
    print("Creating ~30 MP4 videos...")
    for _ in range(30):
        n = next_num()
        dt = random_date(START_DATE, END_DATE)
        size = random.randint(10_000_000, 40_000_000)
        make_mp4(dcim / f"IMG_{n:04d}.mp4", dt, size)
        files_created += 1

    # Files OUTSIDE the normal test window (2020-2021)
    print("Creating 5 files outside test date window (2020-2021)...")
    outside_dates = [datetime(2021, 6, 15), datetime(2020, 12, 1),
                     datetime(2020, 6, 1), datetime(2021, 1, 15), datetime(2021, 11, 30)]
    for dt in outside_dates:
        n = next_num()
        make_jpeg(dcim / f"IMG_{n:04d}.jpg", dt, 2_000_000, (128, 128, 128))
        files_created += 1

    # Count only media files (exclude sidecars)
    media_files = [f for f in dcim.iterdir() if f.is_file() and not f.name.endswith(".photovault_meta")]
    total_size = sum(f.stat().st_size for f in media_files)
    print(f"\nMock library created at: {output_dir}")
    print(f"Media files created: {files_created}")
    print(f"Total size: {total_size / 1_073_741_824:.2f} GB")
    print(f"Live Photo pairs: 20")
    print(f"Files outside date window: 5")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate mock iPhone photo library for testing")
    parser.add_argument("--output", default="./mock_library", type=Path,
                        help="Output directory (default: ./mock_library)")
    args = parser.parse_args()
    generate(args.output)
