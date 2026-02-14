"""
Generate locales.json for the ubuntu font directory

families in directories listed in DIR_LOCALE_MAP are locale specific
all other families are core
"""

import json
import sys
from pathlib import Path

# allow importing fontutil from parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fontutil import scan_font_dir

FONT_DIR = Path(__file__).parent
OUTPUT = FONT_DIR / "locales.json"

# map font subdirectory names (under truetype/ or opentype/) to BCP 47 locales
DIR_LOCALE_MAP = {
    "abyssinica": ["am"],
    "annapurna": ["hi", "ne"],
    "fonts-beng-extra": ["bn"],
    "fonts-deva-extra": ["hi"],
    "fonts-gujr-extra": ["gu"],
    "fonts-guru-extra": ["pa"],
    "fonts-kalapi": ["gu"],
    "fonts-orya-extra": ["or"],
    "fonts-telu-extra": ["te"],
    "fonts-yrsa-rasa": ["gu"],
    "Gargi": ["hi"],
    "Gubbi": ["kn"],
    "kacst": ["ar"],
    "kacst-one": ["ar"],
    "lao": ["lo"],
    "lohit-assamese": ["as"],
    "lohit-bengali": ["bn"],
    "lohit-devanagari": ["hi"],
    "lohit-gujarati": ["gu"],
    "lohit-kannada": ["kn"],
    "lohit-malayalam": ["ml"],
    "lohit-oriya": ["or"],
    "lohit-punjabi": ["pa"],
    "lohit-tamil": ["ta"],
    "lohit-tamil-classical": ["ta"],
    "lohit-telugu": ["te"],
    "malayalam": ["ml"],
    "Nakula": ["hi"],
    "Navilu": ["kn"],
    "padauk": ["my"],
    "pagul": ["hi"],
    "Sahadeva": ["hi"],
    "samyak": ["hi"],
    "samyak-fonts": ["gu", "ml", "ta"],
    "Sarai": ["hi"],
    "sinhala": ["si"],
    "teluguvijayam": ["te"],
    "tlwg": ["th"],
    "ttf-khmeros": ["km"],
    "ttf-khmeros-core": ["km"],
}


def get_font_subdir(rel_path: str) -> str | None:
    """
    extract the font subdirectory name from a relative path
    paths look like truetype/dejavu/DejaVuSans.ttf
    returns the second component (eg 'dejavu', 'noto')
    """
    parts = Path(rel_path).parts
    if len(parts) >= 2 and parts[0] in ("truetype", "opentype"):
        return parts[1]
    return None


def main():
    print(f"Scanning {FONT_DIR.name}...")
    families = scan_font_dir(FONT_DIR)
    print(f"  {len(families)} families")

    locales: dict[str, list[str]] = {"core": []}

    for family, entries in families.items():
        subdir = get_font_subdir(entries[0]["file"])
        if subdir is None:
            print(f"  warning, no subdir for {family} ({entries[0]['file']})")
            continue

        locale_codes = DIR_LOCALE_MAP.get(subdir)
        if locale_codes is None:
            locales["core"].append(family)
        else:
            for locale in locale_codes:
                locales.setdefault(locale, []).append(family)

    # sort, core first then alphabetical
    result = {"core": sorted(locales["core"])}
    for locale in sorted(k for k in locales if k != "core"):
        result[locale] = sorted(locales[locale])

    with open(OUTPUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nWrote {OUTPUT}")
    print(f"  core: {len(result['core'])} families")
    for locale in sorted(k for k in result if k != "core"):
        print(f"  {locale}: {len(result[locale])} families")


if __name__ == "__main__":
    main()
