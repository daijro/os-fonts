"""
Shared font file parsing utilities
opentype/ttc name table reading and directory scanning
"""

import re
import struct
from pathlib import Path

FONT_EXTENSIONS = {".ttf", ".ttc", ".otf"}


def read_name_table(f, base_offset: int = 0) -> dict[int, str]:
    """
    read the opentype name table from an offset table position
    returns dict of nameID -> string value
    prefers windows platform (3,1), falls back to mac (1)
    """
    start = f.tell()
    sfnt_version = f.read(4)
    if sfnt_version not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"):
        return {}

    num_tables = struct.unpack(">H", f.read(2))[0]
    f.seek(f.tell() + 6)  # skip searchRange, entrySelector, rangeShift

    name_offset = None
    for _ in range(num_tables):
        tag = f.read(4)
        f.seek(f.tell() + 4)  # skip checksum
        offset = struct.unpack(">I", f.read(4))[0]
        f.seek(f.tell() + 4)  # skip length
        if tag == b"name":
            # table record offsets are absolute from file start, even in TTC
            name_offset = offset
            break

    if name_offset is None:
        return {}

    f.seek(name_offset)
    f.seek(f.tell() + 2)  # skip format
    count = struct.unpack(">H", f.read(2))[0]
    string_offset = struct.unpack(">H", f.read(2))[0]

    # collect all name records, prefer windows unicode (platform 3, encoding 1)
    names: dict[int, str] = {}
    records = []
    for _ in range(count):
        platform_id = struct.unpack(">H", f.read(2))[0]
        encoding_id = struct.unpack(">H", f.read(2))[0]
        f.seek(f.tell() + 2)  # skip language ID
        name_id = struct.unpack(">H", f.read(2))[0]
        length = struct.unpack(">H", f.read(2))[0]
        offset = struct.unpack(">H", f.read(2))[0]
        records.append((platform_id, encoding_id, name_id, length, offset))

    for platform_id, encoding_id, name_id, length, offset in records:
        # skip if we already have a windows entry for this nameID
        if name_id in names and platform_id != 3:
            continue

        pos = f.tell()
        f.seek(name_offset + string_offset + offset)
        data = f.read(length)
        f.seek(pos)

        if platform_id == 3 and encoding_id == 1:
            names[name_id] = data.decode("utf-16-be", errors="ignore")
        elif platform_id == 1 and name_id not in names:
            names[name_id] = data.decode("latin-1", errors="ignore")

    return names


def scan_font_metadata(font_path: Path) -> list[dict]:
    """
    extract metadata from all fonts in a file
    returns list of dicts with family, subfamily, version
    for TTC files, returns one entry per font in the collection
    """
    results = []
    try:
        with open(font_path, "rb") as f:
            magic = f.read(4)

            if magic == b"ttcf":
                f.seek(8)  # skip ttcf tag + version
                num_fonts = struct.unpack(">I", f.read(4))[0]
                offsets = [struct.unpack(">I", f.read(4))[0] for _ in range(num_fonts)]

                for offset in offsets:
                    f.seek(offset)
                    names = read_name_table(f, offset)
                    family = names.get(16) or names.get(1)
                    subfamily = names.get(17) or names.get(2)
                    version = names.get(5, "").strip() or None
                    if family:
                        results.append(
                            {
                                "family": family,
                                "subfamily": subfamily,
                                "version": version,
                            }
                        )
            else:
                f.seek(0)
                names = read_name_table(f, 0)
                family = names.get(16) or names.get(1)
                subfamily = names.get(17) or names.get(2)
                version = names.get(5, "").strip() or None
                if family:
                    results.append(
                        {
                            "family": family,
                            "subfamily": subfamily,
                            "version": version,
                        }
                    )
    except Exception:
        pass
    return results


def scan_font_dir(font_dir: Path) -> dict[str, list[dict]]:
    """
    scan a directory tree for font files and build family -> entries map
    returns dict of family -> [{"file", "subfamily", "version"}]
    """
    families: dict[str, list[dict]] = {}

    for font_path in sorted(font_dir.rglob("*")):
        if font_path.suffix.lower() not in FONT_EXTENSIONS:
            continue

        rel_path = str(font_path.relative_to(font_dir))
        entries = scan_font_metadata(font_path)

        for entry in entries:
            family = entry["family"]
            families.setdefault(family, []).append(
                {
                    "file": rel_path,
                    "subfamily": entry["subfamily"],
                    "version": entry["version"],
                }
            )

    # sort and deduplicate within each family
    for fam in families:
        families[fam].sort(key=lambda x: (x["file"], x.get("subfamily", "")))
        seen = set()
        deduped = []
        for e in families[fam]:
            key = (e["file"], e.get("subfamily"))
            if key not in seen:
                seen.add(key)
                deduped.append(e)
        families[fam] = deduped

    return {k: v for k, v in sorted(families.items())}


def build_file_index(families: dict) -> dict[str, list[dict]]:
    """
    build file -> [{family, subfamily, version}] index from a families map
    """
    index: dict[str, list[dict]] = {}
    for fam, entries in families.items():
        for e in entries:
            index.setdefault(e["file"], []).append(
                {
                    "family": fam,
                    "subfamily": e.get("subfamily"),
                    "version": e.get("version"),
                }
            )
    return index
