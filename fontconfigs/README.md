## Fontconfigs

These are FreeType configurations for Firefox/Camoufox to match native font rendering and family defaults on each OS.

> [!NOTE]
> These configs are only for FreeType (Linux only).

Info gathered from [browserleaks.com/fonts](https://browserleaks.com/fonts).

### Family defaults

| Family     | Ubuntu           | Windows 11      | macOS              |
| ---------- | ---------------- | --------------- | ------------------ |
| serif      | Noto Serif       | Times New Roman | Times              |
| sans-serif | Noto Sans        | Arial           | Helvetica          |
| monospace  | DejaVu Sans Mono | Consolas        | Menlo              |
| cursive    | Z003             | Comic Sans MS   | Apple Chancery     |
| fantasy    | Noto Sans        | Arial           | Papyrus            |
| system-ui  | Ubuntu Sans      | Segoe UI        | .AppleSystemUIFont |

<details>
<summary>Other legacy fonts</summary>

##### Linux

| Legacy font              | Goes to          |
| ------------------------ | ---------------- |
| Bitstream Vera Sans Mono | DejaVu Sans Mono |

##### MacOS

| Legacy font   | Goes to            |
| ------------- | ------------------ |
| -apple-system | .AppleSystemUIFont |

##### Windows

| Legacy font        | Goes to              |
| ------------------ | -------------------- |
| Arabic Transparent | Arial                |
| Arial Baltic       | Arial                |
| Arial CE           | Arial                |
| Arial Cyr          | Arial                |
| Arial Greek        | Arial                |
| Arial TUR          | Arial                |
| Helvetica          | Arial                |
| Small Fonts        | Arial                |
| MS Shell Dlg       | Microsoft Sans Serif |
| Helv               | Microsoft Sans Serif |
| MS Sans Serif      | Microsoft Sans Serif |
| MS Shell Dlg 2     | Tahoma               |

</details>

---

### Font metrics

It's not possible to perfectly replicate ClearType or Core Text at the pixel level from FreeType, but these configs attempt to get as close as possible for glyph widths.

#### Rendering

| Setting   | Ubuntu     | Windows 11 | macOS    |
| --------- | ---------- | ---------- | -------- |
| hinting   | true       | true       | false    |
| hintstyle | hintslight | hintfull   | hintnone |
| autohint  | false      | false      | false    |
| antialias | true       | true       | true     |
| lcdfilter | lcddefault | lcddefault | lcdnone  |
| rgba      | rgb        | rgb        | none     |

---

### Camoufox structure

```
browser/
  fonts/             # font files
  fontconfigs/
    <os>/            # linux, windows, or macos
      fonts.conf     # active config
  .fontcache/        # generated font cache (per-instance)
```

---