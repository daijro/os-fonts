"""
Merge fonts from multiple sources (sources.yml) into a unified directory

reads sources.yml to find font directories and optional locale mapping jsons
detects clashing families across sources, resolves by version, and produces
fonts.yml - source -> locale -> families with merged filenames and clash info
families.json - source -> locale -> list of family names
"""

import json
import re
import sys
from pathlib import Path

import yaml

from fontutil import FONT_EXTENSIONS, build_file_index, scan_font_dir

BASE_DIR = Path(__file__).parent
SOURCES_PATH = BASE_DIR / "sources.yml"
FONTS_YML_PATH = BASE_DIR / "fonts.yml"
FAMILIES_JSON_PATH = BASE_DIR / "families.json"
FAMILIES_MIN_PATH = BASE_DIR / "families.min.json"
MERGED_DIR = BASE_DIR / "merged"


def _clean(s: str) -> str:
    """
    strip non alphanumeric characters
    """
    return re.sub(r"[^a-zA-Z0-9]", "", s)


def _make_merged_name(rel_path: str, file_index: dict) -> str:
    """
    generate a clean alphanumeric filename from font metadata
    format Family-Subfamily_Family2-Subfamily2-vVersionDigits.ext
    falls back to cleaned original stem for fonts with no ascii family names
    """
    entries = file_index.get(rel_path, [])
    ext = Path(rel_path).suffix.lower()

    if not entries:
        stem = _clean(Path(rel_path).stem)
        return f"{stem or 'font'}{ext}"

    # deduplicate entries by family+subfamily
    seen = set()
    unique = []
    for e in entries:
        key = (e["family"], e.get("subfamily", ""))
        if key not in seen:
            seen.add(key)
            unique.append(e)
    unique.sort(key=lambda x: (x["family"] or "", x.get("subfamily") or ""))

    # deduplicate family names (ignore subfamily for multi family files)
    unique_families = list(dict.fromkeys(_clean(e["family"] or "") for e in unique))
    unique_families = [f for f in unique_families if f]

    # version strip prefix, truncate at semicolon (drop build metadata),
    # then clean to alphanumeric with underscores for dots
    ver_str = unique[0].get("version", "") or ""
    ver_str = re.sub(r"^Version\s+", "", ver_str, flags=re.IGNORECASE)
    ver_str = ver_str.split(";")[0]
    ver_clean = re.sub(r"[^a-zA-Z0-9.]", "", ver_str).replace(".", "_")

    if len(unique_families) == 1:
        sub = _clean(unique[0].get("subfamily") or "")
        name = f"{unique_families[0]}-{sub}" if sub else unique_families[0]
    elif unique_families:
        # multiple families, try common prefix, fall back to listing or filename
        prefix = unique_families[0]
        for f in unique_families[1:]:
            while prefix and not f.startswith(prefix):
                prefix = prefix[:-1]

        joined = "_".join(unique_families)
        if len(joined) <= 80:
            name = joined
        elif prefix and len(prefix) >= 4:
            name = f"{prefix}-x{len(unique_families)}"
        else:
            name = _clean(Path(rel_path).stem) or "font"
    else:
        # all non ascii family names, fall back to original filename stem
        name = _clean(Path(rel_path).stem) or "font"

    if ver_clean:
        name = f"{name}-v{ver_clean}"

    if len(name) > 200:
        name = name[:200]

    return f"{name}{ext}"


# clash detection and version comparison


def build_clash_report(all_sources: dict[str, dict[str, list[dict]]]) -> dict:
    """
    find font families present in multiple sources
    all_sources is {source_name: {family: [entries]}}
    returns {family: {subfamilies: {sub: {source_name: [entries]}}}}
    """
    file_indexes = {name: build_file_index(fams) for name, fams in all_sources.items()}

    # find families present in 2+ sources
    family_sources: dict[str, set[str]] = {}
    for name, fams in all_sources.items():
        for fam in fams:
            family_sources.setdefault(fam, set()).add(name)

    clashes = {}
    for family in sorted(family_sources):
        sources = family_sources[family]
        if len(sources) < 2:
            continue

        # group by subfamily per source
        sub_by_source: dict[str, dict[str, list[dict]]] = {}
        for src in sources:
            sub_by_source[src] = {}
            for e in all_sources[src][family]:
                sub = e.get("subfamily", "Regular") or "Regular"
                sub_by_source[src].setdefault(sub, []).append(e)

        # find subfamilies in 2+ sources
        subfamilies = {}
        all_subs: set[str] = set()
        for src_subs in sub_by_source.values():
            all_subs.update(src_subs.keys())

        for sub in sorted(all_subs):
            present_in = {
                src: sub_by_source[src][sub] for src in sources if sub in sub_by_source[src]
            }
            if len(present_in) < 2:
                continue

            # annotate each entry with also_contains
            annotated = {}
            for src, entries in present_in.items():
                src_entries = []
                for e in entries:
                    entry = dict(e)
                    others = [
                        o
                        for o in file_indexes[src].get(e["file"], [])
                        if o["family"] != family or o["subfamily"] != sub
                    ]
                    if others:
                        entry["also_contains"] = others
                    src_entries.append(entry)
                annotated[src] = src_entries

            subfamilies[sub] = annotated

        if subfamilies:
            clashes[family] = {"subfamilies": subfamilies}

    return clashes


def parse_version(version_str: str | None) -> tuple[int, ...]:
    """
    parse a font version string into a comparable numeric tuple
    strips non numeric characters from each dot separated segment
      "Version 7.03"    -> (7, 3)
      "Version 5.01.2x" -> (5, 1, 2)
      "13.0d1e3"        -> (13, 13)
    """
    if not version_str:
        return (0,)
    s = re.sub(r"^Version\s+", "", version_str, flags=re.IGNORECASE)
    parts = []
    for segment in s.split("."):
        digits = re.sub(r"[^0-9]", "", segment)
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


# merging sources into a single directory


def build_merged(
    clash_report: dict, all_sources: dict[str, dict], sources_config: dict, merged_dir: Path
) -> dict:
    """
    build a merged font directory from multiple sources
    picks the latest version for clashing families across sources
    if a losing file also serves non clashing families, it's kept
    """
    import shutil

    if merged_dir.exists():
        shutil.rmtree(merged_dir)
    merged_dir.mkdir(parents=True, exist_ok=True)

    file_indexes = {name: build_file_index(fams) for name, fams in all_sources.items()}
    clashing_families = set(clash_report.keys())

    # determine winners and skip candidates per source
    skip_candidates: dict[str, set[str]] = {name: set() for name in all_sources}
    winners = []

    for family, info in clash_report.items():
        for sub, sources in info["subfamilies"].items():
            # find source with latest version (earlier sources win ties)
            best_ver = (-1,)
            winner = None
            for src, entries in sources.items():
                ver = parse_version(entries[0]["version"])
                if ver > best_ver:
                    best_ver = ver
                    winner = src

            versions = {src: entries[0].get("version") for src, entries in sources.items()}

            for src, entries in sources.items():
                if src != winner:
                    for e in entries:
                        skip_candidates[src].add(e["file"])

            winners.append(
                {
                    "family": family,
                    "subfamily": sub,
                    "winner": winner,
                    "versions": versions,
                }
            )

    # don't skip files that also serve non clashing families
    actual_skips: dict[str, set[str]] = {}
    for name in all_sources:
        actual = set()
        for f in skip_candidates[name]:
            other_families = {e["family"] for e in file_indexes[name].get(f, [])}
            if not (other_families - clashing_families):
                actual.add(f)
        actual_skips[name] = actual

    # copy files from all sources
    used_names: dict[str, str] = {}  # new_name -> file_key
    stats: dict[str, dict[str, int]] = {}

    for name in all_sources:
        cfg = sources_config[name]
        source_dir = BASE_DIR / cfg["dir"]
        file_idx = file_indexes[name]
        skip = actual_skips[name]
        copied = 0
        skipped = 0

        for f in sorted(source_dir.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in FONT_EXTENSIONS:
                continue
            file_key = str(f.relative_to(source_dir))
            if file_key in skip:
                skipped += 1
                continue

            new_name = _make_merged_name(file_key, file_idx)
            if new_name in used_names:
                stem, ext = new_name.rsplit(".", 1)
                i = 2
                while f"{stem}-{i}.{ext}" in used_names:
                    i += 1
                new_name = f"{stem}-{i}.{ext}"

            used_names[new_name] = file_key
            shutil.copy2(f, merged_dir / new_name)
            copied += 1

        stats[name] = {"copied": copied, "skipped": skipped}

    return {"winners": winners, "stats": stats, "used_names": used_names}


# fonts.yml and families.json output


def build_fonts_data(locale_maps: dict[str, dict], clash_report: dict, used_names: dict) -> dict:
    """
    build fonts data with source -> locale -> family -> entries with merged filenames
    entries for clashed families include source info showing which source won
    and the original files/versions from all clashing sources
    """
    # invert used_names to original_key -> merged_name
    name_map = {v: k for k, v in used_names.items()}

    # build clash lookup (family, sub) -> clash details + merged filename
    clash_lookup: dict[tuple, dict] = {}
    for family, info in clash_report.items():
        for sub, sources in info["subfamilies"].items():
            best_ver = (-1,)
            winner = None
            for src, entries in sources.items():
                ver = parse_version(entries[0]["version"])
                if ver > best_ver:
                    best_ver = ver
                    winner = src

            winning_file = sources[winner][0]["file"]
            merged_name = name_map.get(winning_file, winning_file)

            clash_lookup[(family, sub)] = {
                "winner": winner,
                "merged_file": merged_name,
                "winner_version": sources[winner][0].get("version"),
                "clashed": {
                    src: {
                        "file": entries[0]["file"],
                        "version": entries[0].get("version"),
                    }
                    for src, entries in sources.items()
                },
            }

    def _process_locale_map(locale_map, source_name):
        result = {}
        for locale, families in locale_map.items():
            locale_result = {}
            for family, entries in sorted(families.items()):
                family_entries = []
                for e in entries:
                    sub = e.get("subfamily") or "Regular"
                    clash_key = (family, sub)

                    if clash_key in clash_lookup:
                        clash = clash_lookup[clash_key]
                        entry = {
                            "subfamily": sub,
                            "file": clash["merged_file"],
                            "version": clash["winner_version"],
                            "source": {
                                "was_clashed": True,
                                "from": clash["winner"],
                                "original": e["file"],
                                "clashed": {s: dict(v) for s, v in clash["clashed"].items()},
                            },
                        }
                    else:
                        merged_file = name_map.get(e["file"], e["file"])
                        entry = {
                            "subfamily": sub,
                            "file": merged_file,
                            "version": e.get("version"),
                            "source": {
                                "was_clashed": False,
                                "from": source_name,
                                "original": e["file"],
                            },
                        }

                    family_entries.append(entry)
                locale_result[family] = family_entries
            result[locale] = locale_result
        return result

    return {name: _process_locale_map(lm, name) for name, lm in locale_maps.items()}


def main():
    if not SOURCES_PATH.exists():
        print(f"Error: {SOURCES_PATH} not found", file=sys.stderr)
        sys.exit(1)

    with open(SOURCES_PATH) as f:
        sources_config = yaml.safe_load(f) or {}

    if not sources_config:
        print("No sources configured in sources.yml", file=sys.stderr)
        sys.exit(1)

    all_families: dict[str, dict[str, list[dict]]] = {}
    locale_maps: dict[str, dict] = {}

    # process each source
    for name, cfg in sources_config.items():
        source_dir = BASE_DIR / cfg["dir"]

        if not source_dir.exists():
            print(f"[{name}] {source_dir} not found", file=sys.stderr)
            sys.exit(1)

        families = scan_font_dir(source_dir)
        all_families[name] = families

        # load locale map if provided, otherwise treat all fonts as core
        locales_path = cfg.get("locales")
        if locales_path:
            locales_file = BASE_DIR / locales_path
            if not locales_file.exists():
                print(
                    f"[{name}] {locales_file} not found, generate it first",
                    file=sys.stderr,
                )
                sys.exit(1)
            with open(locales_file) as f:
                locale_names = json.load(f)
            locale_map = {}
            for locale, fam_names in locale_names.items():
                locale_map[locale] = {fam: families[fam] for fam in fam_names if fam in families}
            locale_maps[name] = locale_map
            locale_count = len(locale_map) - 1  # exclude core
            print(f"[{name}] {len(families)} families, {locale_count} locales")
        else:
            locale_maps[name] = {"core": families}
            entry_count = sum(len(v) for v in families.values())
            print(f"[{name}] {len(families)} families, {entry_count} entries")

    if not all_families:
        print("No font sources found", file=sys.stderr)
        sys.exit(1)

    # clash detection
    clashes = build_clash_report(all_families) if len(all_families) >= 2 else {}
    if clashes:
        print(f"\nClashing families: {len(clashes)}")

    # merge
    merge_result = build_merged(clashes, all_families, sources_config, MERGED_DIR)

    print(f"\nMerged -> {MERGED_DIR.name}/")
    for src, s in merge_result["stats"].items():
        print(f"  [{src}] {s['copied']} copied, {s['skipped']} skipped")

    for w in merge_result["winners"]:
        versions = ", ".join(f"{s}={v}" for s, v in w["versions"].items())
        print(f"  {w['family']} / {w['subfamily']}: {w['winner']} wins ({versions})")

    # build fonts.yml
    fonts_data = build_fonts_data(locale_maps, clashes, merge_result["used_names"])

    with open(FONTS_YML_PATH, "w") as f:
        yaml.dump(fonts_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # build families output
    families_data = {
        src: {loc: sorted(fams.keys()) for loc, fams in locales.items()}
        for src, locales in fonts_data.items()
    }
    with open(FAMILIES_JSON_PATH, "w") as f:
        json.dump(families_data, f, indent=2, ensure_ascii=False)
    with open(FAMILIES_MIN_PATH, "w") as f:
        json.dump(families_data, f, separators=(",", ":"))

    clashed_count = sum(
        1
        for src in fonts_data.values()
        for loc in src.values()
        for fam_entries in loc.values()
        for e in fam_entries
        if isinstance(e, dict) and e.get("source", {}).get("was_clashed")
    )

    total_files = len(merge_result["used_names"])
    print(f"\nOutput:")
    print(f"  {FONTS_YML_PATH.name}")
    print(f"  {FAMILIES_JSON_PATH.name}")
    print(f"  {FAMILIES_MIN_PATH.name}")
    print(f"  {MERGED_DIR.name}/  {total_files} files")
    if clashed_count:
        print(f"  Clashed entries: {clashed_count}")


if __name__ == "__main__":
    main()
