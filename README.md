# OS Fonts

All of the latest Windows, MacOS, and common Linux system fonts, & additional language fonts. Merged and deduped into a single directory.

<hr width=50>

### Includes

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
  - Miscellaneous fonts from older Microsoft releases & other collections
---

# Sources

### Windows 26H1

Windows 11 fonts are downloaded from the language feature packs from the UUP dump API. Font packages are mapped to each locale using Microsoft's [Features on Demand spreadsheet](https://learn.microsoft.com/en-us/azure/virtual-desktop/windows-11-language-packs).

The downloader is included in `win11/`


### Ubuntu

Base fonts are extracted from a fresh Ubuntu 24.04 system with all of the default office packages.

Other locale-specific fonts for Indic, Thai, Arabic, etc were installed using this command:

```bash
sudo apt install fonts-indic fonts-thai-tlwg fonts-kacst fonts-kacst-one \
  fonts-khmeros fonts-sil-padauk fonts-lao fonts-noto-cjk fonts-noto-core \
  fonts-noto-color-emoji fonts-sil-abyssinica fonts-lklug-sinhala
```

Fonts were then extracted from `/usr/share/fonts/`

### MacOS

Fonts are extracted from macOS Tahoe. MacOS includes locale-specific fonts altogether, so no additional packages are required.

The Apple Color Emoji font was huge (188mb) so I converted each emoji to just silhouette shapes. This brought it down to ~13.5mb and keeps the ligature measurements the same. The script is included in `macos-tahoe/AppleColorEmoji/to_silhouette.py`.

### Extras

Miscellaneous fonts from older Microsoft releases & other collections. These don't have any locale mapping.

---

## Output

- `merged/` - flat directory with all font files. Fonts are deduped by taking the latest version per family.
- `fonts.yml` - debug output of which fonts were deduped, and each family's file source
- `families.json` - maps locales to avaliable font families

### families.json structure

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
make clean-temp     # remove win11 temp download files
make clean-all      # remove all generated files
```

---

# Disclaimer

> [!WARNING]
> This project is provided for anti-fingerprinting and privacy research purposes only for the purpose of font metric spoofing. These fonts are the property of their respective copyright holders (Microsoft, Apple, etc.). All fonts are the intellectual property of their respective owners.

---