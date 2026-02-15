# OS Fonts

All of the latest Windows, MacOS, and common Linux system fonts, & additional language fonts. Merged and deduped into a single directory.

<hr width=50>

## Fonts

- **Windows 11 26H1**
  - All of the latest bundled fonts
  - All fonts from language feature packages from Windows Update servers
  - Updater script
- **MacOS 26**
  - All of the latest Tahoe system fonts
- **Common Linux fonts**
  - All base Ubuntu 24.04 fonts & from the default packages
  - Fonts from other common language packages in the Ubuntu repos
- **Extra fonts**
  - 150+ font families from commonly installed software & other collections

Also includes FreeType configs for each OS's family defaults (serif, sans-serif, monospace, etc)

---

# Sources

### Windows 26H1

Windows 11 fonts are downloaded from the language feature packs from the UUP dump API. Font packages are mapped to each locale using Microsoft's [Features on Demand spreadsheet](https://learn.microsoft.com/en-us/azure/virtual-desktop/windows-11-language-packs).

The downloader is included in `win11/`

### Ubuntu

Base fonts are extracted from a fresh Ubuntu 24.04 system with all of the default office packages.

Other locale-specific fonts for Indic, Thai, Arabic, etc were extracted from these Debian packages:

<details>
<summary>
See list
</summary>

- [fonts-indic](https://packages.debian.org/sid/fonts/fonts-indic)
- [fonts-thai-tlwg](https://packages.debian.org/sid/fonts/fonts-thai-tlwg)
- [fonts-kacst](https://packages.debian.org/sid/fonts/fonts-kacst)
- [fonts-kacst-one](https://packages.debian.org/sid/fonts/fonts-kacst-one)
- [fonts-khmeros](https://packages.debian.org/sid/fonts/fonts-khmeros)
- [fonts-sil-padauk](https://packages.debian.org/sid/fonts/fonts-sil-padauk)
- [fonts-lao](https://packages.debian.org/sid/fonts/fonts-lao)
- [fonts-noto-cjk](https://packages.debian.org/sid/fonts/fonts-noto-cjk)
- [fonts-noto-core](https://packages.debian.org/sid/fonts/fonts-noto-core)
- [fonts-noto-color-emoji](https://packages.debian.org/sid/fonts/fonts-noto-color-emoji)
- [fonts-sil-abyssinica](https://packages.debian.org/sid/fonts/fonts-sil-abyssinica)
- [fonts-lklug-sinhala](https://packages.debian.org/sid/fonts/fonts-lklug-sinhala)

</details>

### MacOS

Fonts are extracted from macOS Tahoe. MacOS includes locale-specific fonts altogether, so no additional packages are required.

The Apple Color Emoji font was huge (188mb) so I converted each emoji to just silhouette shapes. This brought it down to ~13.5mb and keeps the ligature measurements the same. The script is included in `macos-tahoe/AppleColorEmoji/to_silhouette.py`.

### Extras

Miscellaneous fonts from commonly installed software and font collections. These were found by searching through massive font archives for families that appeared in the wild 10+ times in [fpgen](https://github.com/scrapfly/fingerprint-generator)'s font name dataset.

---

## Output

- `merged/` - flat directory with all font files. Fonts are deduped by taking the latest version per family.
- `merge.yml` - debug output of which fonts were deduped, and each family's file source
- `font-map.json` - maps locales to available font families

### font-map.json structure

```json
{
  "win11": {
    "core": ["Arial", "Calibri", ...],
    "ar": ["Arabic Font", ...],
    "ja": ["Japanese Font", ...]
  }
}
```

Each source has a `core` key for fonts available in all locales, and optional locale-specific fonts.

---

## Usage

Download and extract fonts, then map the font families to locale codes:

```
make win11
make build-locales
```

Create the merged output folder:

```
make merge
```

Run everything:

```
make all
```

Clean up:

```
make clean-temp     # remove temp files
make clean-all      # remove all generated files
```

---

# Disclaimer

> [!WARNING]
> This project is provided for anti-fingerprinting and privacy research purposes only for the purpose of font metric spoofing. These fonts are the property of their respective copyright holders (Microsoft, Apple, etc.). All fonts are the intellectual property of their respective owners.

---
