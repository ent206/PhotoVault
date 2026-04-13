#!/usr/bin/env python3
"""Debug script: dumps date distribution from the Photos DB on the connected iPhone."""
import asyncio
import os
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime

_COREDATA_OFFSET = 978_307_200


async def main():
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    print("Connecting to iPhone...")
    lockdown = await create_using_usbmux()
    print(f"Connected: {lockdown.display_name}")

    afc = AfcService(lockdown=lockdown)

    print("Downloading Photos.sqlite...")
    db_bytes = None
    for path in ("/PhotoData/Photos.sqlite", "/PhotoData/database/Photos.sqlite"):
        try:
            data = await afc.get_file_contents(path)
            if data and len(data) > 1024:
                db_bytes = bytes(data)
                print(f"  Found ({len(db_bytes):,} bytes)")
                break
        except Exception:
            continue

    if not db_bytes:
        print("ERROR: Could not download Photos.sqlite")
        return

    await afc.aclose()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "Photos.sqlite")
        with open(db_path, "wb") as f:
            f.write(db_bytes)

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()

        tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        tbl = "ZASSET" if "ZASSET" in tables else "ZGENERICASSET"

        rows = cur.execute(
            f"SELECT ZDATECREATED FROM {tbl} WHERE ZTRASHEDSTATE=0 AND ZDATECREATED IS NOT NULL"
        ).fetchall()
        conn.close()

    year_counts = Counter()
    for (ts,) in rows:
        try:
            year_counts[datetime.fromtimestamp(ts + _COREDATA_OFFSET).year] += 1
        except Exception:
            pass

    total = sum(year_counts.values())
    print(f"\nPhotos per year ({total:,} total):\n")
    for year in sorted(year_counts):
        print(f"  {year}: {year_counts[year]:,}")


asyncio.run(main())
