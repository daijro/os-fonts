"""
Windows 11 font downloader
downloads and extracts fonts from windows 11 UUP packages

commands
  download  download font packages from UUP
  extract   extract fonts from downloaded packages
  clean     remove temporary files
"""

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests

# import fontutil from parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fontutil import FONT_EXTENSIONS, read_name_table

WIN11_DIR = Path(__file__).parent
TEMP_DIR = WIN11_DIR / "temp"

WINDOWS_VERSION = "26H1"

CORE_ESD_NAME = "Microsoft-Windows-Client-Desktop-Required-Package.esd"


def parse_fontlist(fontlist_path: Path) -> set[str]:
    """
    parse fontlist.md and extract all expected font filenames (lowercase)
    """
    if not fontlist_path.exists():
        return set()

    font_files = set()
    with open(fontlist_path) as f:
        content = f.read()

    table_pattern = re.compile(r"\|\s*[^|]+\s*\|\s*[^|]+\s*\|\s*([^|]+)\s*\|\s*[^|]+\s*\|")

    for match in table_pattern.finditer(content):
        filename = match.group(1).strip()
        if filename and filename != "File Name" and not filename.startswith("---"):
            filename = filename.replace("\\_", "_")
            font_files.add(filename.lower())

    return font_files


def _parse_version_slug(version_str: str) -> str | None:
    """
    extract a version slug like '7_03' from a version string
    """
    match = re.search(r"(\d+)\.(\d+)", version_str)
    if match:
        major, minor = match.groups()
        return f"{major}_{minor.ljust(2, '0')[:2]}"
    return None


def get_all_font_metadata(font_path: Path) -> list[dict]:
    """
    extract metadata from all fonts in a file
    returns list of dicts with family, subfamily, version, version_slug
    for TTC files, returns one entry per font in the collection
    """
    results = []
    try:
        with open(font_path, "rb") as f:
            magic = f.read(4)

            if magic == b"ttcf":
                f.seek(8)
                num_fonts = struct.unpack(">I", f.read(4))[0]
                if num_fonts == 0:
                    return results
                offsets = [struct.unpack(">I", f.read(4))[0] for _ in range(num_fonts)]

                for offset in offsets:
                    f.seek(offset)
                    names = read_name_table(f, offset)
                    family = names.get(16) or names.get(1)
                    subfamily = names.get(17) or names.get(2)
                    version_str = names.get(5)
                    version = version_str.strip() if version_str else None
                    slug = _parse_version_slug(version_str) if version_str else None
                    if family:
                        results.append(
                            {
                                "family": family,
                                "subfamily": subfamily,
                                "version": version,
                                "version_slug": slug,
                            }
                        )
            else:
                f.seek(0)
                names = read_name_table(f, 0)
                family = names.get(16) or names.get(1)
                subfamily = names.get(17) or names.get(2)
                version_str = names.get(5)
                version = version_str.strip() if version_str else None
                slug = _parse_version_slug(version_str) if version_str else None
                if family:
                    results.append(
                        {
                            "family": family,
                            "subfamily": subfamily,
                            "version": version,
                            "version_slug": slug,
                        }
                    )
    except Exception:
        pass
    return results


class UUPDumpAPI:
    def __init__(self):
        self.base_url = "https://api.uupdump.net"
        self.session = requests.Session()
        self.request_delay = 2.0
        self.last_request_time = 0.0

    def _request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """
        make a request to the api with rate limiting
        """
        url = f"{self.base_url}/{endpoint}"
        max_retries = 5
        delay = self.request_delay

        for attempt in range(max_retries):
            elapsed = time.time() - self.last_request_time
            if elapsed < delay:
                time.sleep(delay - elapsed)

            try:
                self.last_request_time = time.time()
                resp = self.session.get(url, params=params, timeout=60)

                if resp.status_code == 429:
                    delay = min(delay * 2, 30)
                    print(f"  Rate limited, waiting {delay:.0f}s...", file=sys.stderr)
                    time.sleep(delay)
                    continue

                resp.raise_for_status()
                data = resp.json()
                if "error" in data.get("response", {}):
                    raise Exception(f"API error {data['response']['error']}")

                self.request_delay = max(2.0, self.request_delay * 0.9)
                return data["response"]

            except requests.exceptions.HTTPError:
                if resp.status_code == 429:
                    continue
                raise
            except requests.exceptions.RequestException:
                if attempt < max_retries - 1:
                    delay = min(delay * 2, 30)
                    print(f"  Request failed, retrying in {delay:.0f}s...", file=sys.stderr)
                    time.sleep(delay)
                else:
                    raise

        raise Exception(f"Max retries exceeded for {endpoint}")

    def list_builds(self, search: str) -> dict:
        """
        list available builds filtered by search query
        """
        params = {"sortByDate": 1, "search": search}
        return self._request("listid.php", params).get("builds", {})

    def get_files(self, update_id: str) -> dict:
        """
        get file list and download links for an update
        """
        return self._request("get.php", {"id": update_id})


# download and extraction


def find_font_packages(files: dict) -> dict:
    """
    filter files to find font related CAB packages, excluding deltas
    """
    font_packages = {}
    delta_pattern = re.compile(r"_[a-f0-9]{8}\.cab$", re.IGNORECASE)

    for filename, info in files.items():
        if delta_pattern.search(filename):
            continue
        if "languagefeatures-fonts-" in filename.lower() and filename.lower().endswith(".cab"):
            font_packages[filename] = info
    return font_packages


def download_file(url: str, dest: Path, sha1: Optional[str] = None) -> bool:
    """
    download a file with optional SHA1 verification
    """
    try:
        resp = requests.get(url, stream=True, timeout=300)
        resp.raise_for_status()

        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        if sha1:
            with open(dest, "rb") as f:
                file_hash = hashlib.sha1(f.read(), usedforsecurity=False).hexdigest()
            if file_hash.lower() != sha1.lower():
                print(f"  SHA1 mismatch for {dest.name}", file=sys.stderr)
                dest.unlink()
                return False

        return True
    except Exception as e:
        print(f"  Error downloading {dest.name}: {e}", file=sys.stderr)
        return False


def extract_archive(archive_path: Path, extract_dir: Path) -> bool:
    """
    extract an archive (CAB, ESD, WIM) using 7z or cabextract
    """
    extract_dir.mkdir(parents=True, exist_ok=True)

    if archive_path.suffix.lower() in (".esd", ".wim"):
        if shutil.which("7z"):
            result = subprocess.run(
                ["7z", "x", f"-o{extract_dir}", str(archive_path), "-y"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        print("7z is required for ESD/WIM extraction", file=sys.stderr)
        return False

    if shutil.which("cabextract"):
        result = subprocess.run(
            ["cabextract", "-d", str(extract_dir), str(archive_path)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    if shutil.which("7z"):
        result = subprocess.run(
            ["7z", "x", f"-o{extract_dir}", str(archive_path), "-y"], capture_output=True, text=True
        )
        return result.returncode == 0

    print("Neither cabextract nor 7z found", file=sys.stderr)
    return False


def collect_fonts(
    source_dir: Path, dest_dir: Path, expected_fonts: Optional[set[str]] = None
) -> list[dict]:
    """
    recursively find font files and copy to dest with versioned names
    returns list of font info dicts with file, family, subfamily, version, sha256
    for TTC files with multiple families, returns one entry per family
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    collected = []
    seen_files = set()

    for ext in FONT_EXTENSIONS:
        for font_file in source_dir.rglob(f"*{ext}"):
            font_name_lower = font_file.name.lower()

            if expected_fonts and font_name_lower not in expected_fonts:
                continue

            all_meta = get_all_font_metadata(font_file)
            if not all_meta:
                continue

            # use first font's version for the output filename
            first = all_meta[0]
            stem = font_file.stem.lower()
            ext_lower = font_file.suffix.lower()
            slug = first["version_slug"]
            dest_name = f"{stem}{slug}{ext_lower}" if slug else f"{stem}{ext_lower}"

            if dest_name in seen_files:
                continue
            seen_files.add(dest_name)

            sha256 = hashlib.sha256(font_file.read_bytes()).hexdigest()
            shutil.copy2(font_file, dest_dir / dest_name)

            # one entry per family in the file
            seen_families = set()
            for meta in all_meta:
                fam_key = (meta["family"], meta["subfamily"])
                if fam_key in seen_families:
                    continue
                seen_families.add(fam_key)
                collected.append(
                    {
                        "file": dest_name,
                        "family": meta["family"],
                        "subfamily": meta["subfamily"],
                        "version": meta["version"],
                        "sha256": sha256,
                    }
                )

    return sorted(collected, key=lambda x: x["file"])


def find_build(api: UUPDumpAPI, search: str, arch: str = "amd64") -> Optional[dict]:
    """
    find the latest windows 11 build for the target architecture
    """
    builds = api.list_builds(search=search)
    if not builds:
        print(f"No builds found for '{search}'", file=sys.stderr)
        return None

    for build_id, build_info in builds.items():
        if arch in build_info.get("arch", ""):
            build_info["uuid"] = build_info.get("uuid", build_id)
            return build_info

    print(f"No {arch} builds found", file=sys.stderr)
    return None


def cmd_download(args):
    """
    download windows 11 language font packages and core ESD
    """
    api = UUPDumpAPI()
    search = WINDOWS_VERSION

    print("Windows 11 Font Downloader")
    print("=" * 40)
    print(f"Search: {search}")
    print()

    print("[1/4] Searching for builds...")
    build = find_build(api, search)
    if not build:
        sys.exit(1)
    print(f"  Found: {build['title']}")
    print(f"  UUID: {build['uuid']}")
    print()

    print("[2/4] Fetching file list...")
    files_response = api.get_files(build["uuid"])
    all_files = files_response.get("files", {})
    print(f"  Total files in update: {len(all_files)}")

    # language font packages
    font_packages = find_font_packages(all_files)
    print(f"  Found {len(font_packages)} language font packages")

    # core ESD
    has_core = CORE_ESD_NAME in all_files
    if has_core:
        core_size = int(all_files[CORE_ESD_NAME].get("size", 0)) / (1024 * 1024)
        print(f"  Found core ESD ({core_size:.0f} MB)")
    else:
        print(f"  Warning, core ESD not found in build", file=sys.stderr)

    total_size = sum(int(p.get("size", 0)) for p in font_packages.values())
    if has_core:
        total_size += int(all_files[CORE_ESD_NAME].get("size", 0))
    print(f"  Total download size: {total_size / (1024 * 1024):.1f} MB")
    print()

    # download language font packages
    print("[3/4] Downloading language font packages...")
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    failed = 0

    for i, (pkg_name, pkg_info) in enumerate(sorted(font_packages.items()), 1):
        size_mb = int(pkg_info.get("size", 0)) / (1024 * 1024)
        print(f"  [{i}/{len(font_packages)}] {pkg_name} ({size_mb:.1f} MB)")

        url = pkg_info.get("url")
        if not url:
            print(f"    No download URL available")
            failed += 1
            continue

        dest_path = TEMP_DIR / pkg_name
        if dest_path.exists():
            print(f"    Already downloaded, skipping")
            downloaded += 1
            continue

        if download_file(url, dest_path, pkg_info.get("sha1")):
            print(f"    OK")
            downloaded += 1
        else:
            print(f"    FAILED")
            failed += 1

    print(f"  {downloaded} succeeded, {failed} failed")
    print()

    # download core ESD
    if has_core:
        print("[4/4] Downloading core ESD...")
        dest_path = TEMP_DIR / CORE_ESD_NAME
        if dest_path.exists():
            print(f"  Already downloaded, skipping")
        else:
            esd_info = all_files[CORE_ESD_NAME]
            url = esd_info.get("url")
            if not url:
                print(f"  No download URL", file=sys.stderr)
            else:
                print(f"  Downloading {core_size:.0f} MB...")
                if download_file(url, dest_path, esd_info.get("sha1")):
                    print(f"  OK")
                else:
                    print(f"  FAILED")
    else:
        print("[4/4] Skipping core ESD (not found)")
    print()

    print("Download complete!")
    print(f"Files saved to: {TEMP_DIR.absolute()}")


def _short_pkg(name: str) -> str:
    """
    shorten a package name for display
    """
    if name == CORE_ESD_NAME:
        return "core"
    m = re.search(r"Fonts-([^-]+)-Package", name)
    return m.group(1) if m else name


def cmd_extract(args):
    """
    extract fonts from downloaded packages into output directory
    """
    output_dir = WIN11_DIR / WINDOWS_VERSION
    extraction_map_path = WIN11_DIR / "extraction.json"
    fontlist_path = WIN11_DIR.parent.parent / "ms_docs" / "win11.md"

    print("Windows 11 Font Downloader")
    print("=" * 40)
    print()

    # parse expected fonts from fontlist
    expected_fonts = parse_fontlist(fontlist_path)
    if expected_fonts:
        print(f"Loaded {len(expected_fonts)} expected fonts from {fontlist_path.name}")
    else:
        print(f"No fontlist found, extracting all fonts")
    print()

    # clear output directory
    if output_dir.exists():
        shutil.rmtree(output_dir)

    # phase 1 extract all fonts from all packages into staging
    raw_packages: dict[str, list[dict]] = {}
    total_fonts = 0

    # extract CAB files (language fonts)
    cab_files = list(TEMP_DIR.glob("*.cab"))
    if cab_files:
        print(f"Extracting {len(cab_files)} language font packages...")
        extract_base = TEMP_DIR / "extracted"

        for i, cab_path in enumerate(sorted(cab_files), 1):
            cab_name = cab_path.name
            print(f"  [{i}/{len(cab_files)}] {cab_name}")
            extract_dir = extract_base / cab_path.stem

            staging = TEMP_DIR / "staging" / cab_path.stem

            if extract_archive(cab_path, extract_dir):
                fonts = collect_fonts(
                    extract_dir, staging, expected_fonts if expected_fonts else None
                )
                raw_packages[cab_name] = fonts
                print(f"      -> {len(fonts)} fonts")
                total_fonts += len(fonts)
    print()

    # extract ESD file (core fonts)
    esd_path = TEMP_DIR / CORE_ESD_NAME
    if esd_path.exists():
        print("Extracting core ESD...")
        esd_extract_dir = TEMP_DIR / "esd_extracted"

        if not esd_extract_dir.exists():
            if not extract_archive(esd_path, esd_extract_dir):
                print(f"  Failed to extract ESD", file=sys.stderr)
            else:
                print(f"  Extracted")
        else:
            print(f"  Already extracted")

        staging = TEMP_DIR / "staging" / "core"
        fonts = collect_fonts(esd_extract_dir, staging, expected_fonts if expected_fonts else None)
        raw_packages[CORE_ESD_NAME] = fonts
        print(f"  -> {len(fonts)} core fonts")
        total_fonts += len(fonts)
    print()

    # phase 2 deduplicate by file
    # build file -> [(package, [font_infos])] index
    file_index: dict[str, list[tuple[str, list[dict]]]] = {}
    for pkg_name, fonts in raw_packages.items():
        pkg_files: dict[str, list[dict]] = {}
        for font_info in fonts:
            pkg_files.setdefault(font_info["file"], []).append(font_info)
        for fname, infos in pkg_files.items():
            file_index.setdefault(fname, []).append((pkg_name, infos))

    # find duplicates (same file in multiple packages) and decide where each lives
    duplicates = []
    deduped_packages: dict[str, list[dict]] = {pkg: [] for pkg in raw_packages}

    for fname, pkg_entries in file_index.items():
        if len(pkg_entries) == 1:
            pkg, infos = pkg_entries[0]
            deduped_packages[pkg].extend(infos)
            continue

        # same file in multiple packages
        pkgs = [e[0] for e in pkg_entries]
        all_infos = pkg_entries[0][1]
        families = [i["family"] for i in all_infos]
        duplicates.append(
            {
                "file": fname,
                "families": families,
                "version": all_infos[0]["version"],
                "packages": [_short_pkg(p) for p in pkgs],
            }
        )

        # keep in core if present, otherwise first package
        if CORE_ESD_NAME in pkgs:
            deduped_packages[CORE_ESD_NAME].extend(all_infos)
        else:
            deduped_packages[pkgs[0]].extend(all_infos)

    # sort fonts within each package
    for pkg in deduped_packages:
        deduped_packages[pkg].sort(key=lambda x: x["file"])

    # phase 3 copy deduped fonts to output
    copied_files: set[str] = set()
    for pkg_name, fonts in deduped_packages.items():
        if not fonts:
            continue

        output_dir.mkdir(parents=True, exist_ok=True)

        if pkg_name == CORE_ESD_NAME:
            staging = TEMP_DIR / "staging" / "core"
        else:
            staging = TEMP_DIR / "staging" / Path(pkg_name).stem

        for font_info in fonts:
            fname = font_info["file"]
            if fname in copied_files:
                continue
            src = staging / fname
            if src.exists():
                shutil.copy2(src, output_dir / fname)
                copied_files.add(fname)

    # report exact duplicates (same file in multiple packages)
    if duplicates:
        print(f"Exact duplicates removed ({len(duplicates)} files across packages)")
        for d in sorted(duplicates, key=lambda x: x["file"]):
            core_pkgs = [p for p in d["packages"] if p == "core"]
            kept = "core" if core_pkgs else d["packages"][0]
            print(f"  {d['file']}")
            print(f"    Families  {', '.join(d['families'])}")
            print(f"    Version   {d['version']}")
            print(f"    In        {', '.join(d['packages'])}")
            print(f"    Kept in   {kept}")
        print()

    # check for same font family in different files (possibly different versions)
    family_files: dict[str, list[tuple[str, dict]]] = {}
    for pkg_name, fonts in deduped_packages.items():
        for font_info in fonts:
            family = font_info.get("family")
            if family:
                if family not in family_files:
                    family_files[family] = []
                family_files[family].append((_short_pkg(pkg_name), font_info))

    # filter to families spanning different packages (cross package dupes)
    cross_pkg_dupes = {}
    for fam, entries in family_files.items():
        pkgs = set(e[0] for e in entries)
        if len(pkgs) > 1:
            cross_pkg_dupes[fam] = entries

    if cross_pkg_dupes:
        print(f"Same font family across different packages ({len(cross_pkg_dupes)} families)")
        for family in sorted(cross_pkg_dupes):
            entries = cross_pkg_dupes[family]
            print(f"  {family}")
            for pkg, info in sorted(entries, key=lambda x: (x[0], x[1]["file"])):
                print(f"    {info['file']}  v{info['version']}  [{pkg}]")
        print()

    # build extraction map (deduped, with metadata)
    extraction_map = {}
    for pkg_name, fonts in deduped_packages.items():
        if fonts:
            extraction_map[pkg_name] = fonts

    with open(extraction_map_path, "w") as f:
        json.dump(extraction_map, f, indent=2)

    deduped_total = sum(len(f) for f in deduped_packages.values())
    print(f"Extraction complete!")
    print(f"  Total fonts (before dedup)  {total_fonts}")
    print(f"  Total fonts (after dedup)   {deduped_total}")
    print(f"  Exact duplicates removed    {len(duplicates)}")
    print(f"  Extraction map  {extraction_map_path}")
    print(f"  Output  {output_dir.absolute()}")


def cmd_all(args):
    """
    run full pipeline, download and extract
    """
    cmd_download(args)
    cmd_extract(args)


def cmd_clean(args):
    """
    clean temporary files
    """
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
        print(f"Cleaned: {TEMP_DIR}")
    else:
        print("Nothing to clean")


def main():
    parser = argparse.ArgumentParser(description="Windows 11 Font Downloader")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    dl_parser = subparsers.add_parser("download", help="Download font packages and core ESD")
    dl_parser.set_defaults(func=cmd_download)

    ex_parser = subparsers.add_parser("extract", help="Extract fonts from downloaded packages")
    ex_parser.set_defaults(func=cmd_extract)

    all_parser = subparsers.add_parser("all", help="Run full pipeline (download + extract)")
    all_parser.set_defaults(func=cmd_all)

    cl_parser = subparsers.add_parser("clean", help="Clean temporary files")
    cl_parser.set_defaults(func=cmd_clean)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
