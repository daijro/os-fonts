"""
Generate locales.json from extraction map + FOD locale mapping

maps CAB package names to BCP 47 locales using the microsoft FOD spreadsheet
core fonts come from the ESD package, locale fonts from language feature CABs
"""

import json
import re
import sys
from pathlib import Path

import requests

WIN11_DIR = Path(__file__).parent
EXTRACTION_MAP = WIN11_DIR / "extraction.json"
XLSX_PATH = WIN11_DIR / "fod-mapping.xlsx"
OVERRIDE_PATH = WIN11_DIR / "override.yml"
LOCALES_PATH = WIN11_DIR / "locales.json"

CORE_ESD_NAME = "Microsoft-Windows-Client-Desktop-Required-Package.esd"
XLSX_URL = "https://download.microsoft.com/download/7/6/0/7600F9DC-C296-4CF8-B92A-2D85BAFBD5D2/Windows-10-1809-FOD-to-LP-Mapping-Table.xlsx"


def _normalize_cab_name(cab_name: str) -> str:
    """
    normalize a CAB name, strip .cab and cpu arch suffix
    """
    name = cab_name.removesuffix(".cab")
    return re.sub(r"-(amd64|arm64|x86)$", "", name)


def _parse_fod_mapping() -> dict[str, list[str]]:
    """
    parse FOD mapping spreadsheet, returns normalized_cab_name -> sorted locales
    """
    import openpyxl

    if not XLSX_PATH.exists():
        print(f"Downloading FOD mapping spreadsheet...")
        resp = requests.get(XLSX_URL, timeout=60)
        resp.raise_for_status()
        XLSX_PATH.write_bytes(resp.content)
        print(f"  Saved to {XLSX_PATH}")

    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
    ws = wb.active
    mapping: dict[str, set[str]] = {}

    for row in ws.iter_rows(min_row=2, values_only=True):
        cab_name, _source, target_locale, _lang_group, fod_area, _trigger = row
        if not fod_area or fod_area != "Fonts":
            continue
        if not cab_name or not target_locale or target_locale == "n/a":
            continue
        if "LeanDesktop" in cab_name:
            continue
        key = _normalize_cab_name(cab_name)
        mapping.setdefault(key, set()).add(target_locale)

    wb.close()
    return {k: sorted(v) for k, v in mapping.items()}


def _load_overrides() -> dict[str, list[str]]:
    """
    load locale override mappings from YAML
    """
    if not OVERRIDE_PATH.exists():
        return {}
    import yaml

    with open(OVERRIDE_PATH) as f:
        data = yaml.safe_load(f) or {}
    return {_normalize_cab_name(k): v for k, v in data.items()}


def main():
    if not EXTRACTION_MAP.exists():
        print(f"{EXTRACTION_MAP} not found, run 'download_utils.py extract' first", file=sys.stderr)
        sys.exit(1)

    with open(EXTRACTION_MAP) as f:
        extraction_map = json.load(f)

    fod_mapping = _parse_fod_mapping()

    # apply overrides
    overrides = _load_overrides()
    if overrides:
        for key, locales in overrides.items():
            fod_mapping[key] = locales
        print(f"Applied {len(overrides)} override(s) from {OVERRIDE_PATH.name}")

    # build locales.json (core + per locale family names)
    core_family_names: set[str] = set()
    for entry in extraction_map.get(CORE_ESD_NAME, []):
        family = entry.get("family")
        if family:
            core_family_names.add(family)

    locale_family_names: dict[str, set[str]] = {}
    for cab_name, font_entries in extraction_map.items():
        if cab_name == CORE_ESD_NAME:
            continue
        key = _normalize_cab_name(cab_name)
        locales = fod_mapping.get(key, [])
        if not locales:
            continue

        pkg_family_names = {e["family"] for e in font_entries if e.get("family")}
        for locale in locales:
            locale_family_names.setdefault(locale, set()).update(pkg_family_names)

    result = {"core": sorted(core_family_names)}
    for locale in sorted(locale_family_names):
        result[locale] = sorted(locale_family_names[locale])

    with open(LOCALES_PATH, "w") as f:
        json.dump(result, f, indent=2)

    locale_count = len(result) - 1
    core_count = len(result["core"])
    print(f"Locales written to {LOCALES_PATH}")
    print(f"  Core families  {core_count}")
    print(f"  Locales  {locale_count}")


if __name__ == "__main__":
    main()
