# MapleOCR

Windows helper workflow for MapleStory: Idle RPG equipment Optical Character Recognition.

## Current baseline

**v193**

MapleOCR v193 includes:

- Equipped screenshots rebuilding the Basic Preset
- fresh bag inventory Optical Character Recognition
- support for mixed progression levels without a fixed minimum main Attack value
- white-first foreground stat reading
- comparison and background bleed filtering
- split and comma-formatted whole-number reconstruction
- targeted main Attack fragment reconstruction
- zero-rounding parser policy
- Defense Penetration parsing
- conservative option-stat and structural validation
- lock-state snapshots from the same screenshot batch
- screenshot capture timestamp and order tracking for Best in Slot LOCK and UNLOCK sorting
- automatic Arena, Colosseum, Maximum Health, Maximum Mana and Chapter Boss preset rebuilding
- generated detail files under `C:\MapleOCR\Results`
- `mapleupload.txt` compatibility copy in `C:\MapleOCR`
- automatic `Output_v193_check.zip` creation after a run
- safe post-optimizer `BIS_stats.zip` builder
- same-run Best in Slot validation using physical equipment data rather than optimizer item identifiers
- handling for optimizer item identifier remapping and cached duplicate equipment rows
- Basic Preset normalization when the optimizer export drifts from the current Equipped Optical Character Recognition snapshot
- preservation of displaced real bag items during Basic Preset normalization
- reusable popup-based MapleOCR directory cleaner

Personal screenshots, optimizer exports, Optical Character Recognition results and generated ZIP files should not be committed to the repository.

## Optimizer

MapleOCR is designed to work with the MapleStory Idle RPG Optimizer:

https://mirpg-optimizer.netlify.app/

After a successful real MapleOCR run, import:

```text
C:\MapleOCR\mapleupload.txt
```

into the optimizer.

After importing, export the updated optimizer data back to:

```text
C:\MapleOCR\mapleexport.txt
```

Then build the Best in Slot handoff ZIP with:

```powershell
cd C:\MapleOCR
.\build_BIS_stats_v193.ps1
```

The builder creates:

```text
C:\MapleOCR\BIS_stats.zip
```

only after validating that the optimizer export is compatible with the current Optical Character Recognition run.

## Optimizer

MapleOCR is designed to work with the MapleStory Idle RPG Optimizer:

https://mirpg-optimizer.netlify.app/

After a successful OCR run, import:

```text
C:\MapleOCR\mapleupload.txt
```

## Run

Dry run:

```powershell
cd C:\MapleOCR
.\run_v193_full_inventory_dry_run.ps1
```

Real run:

```powershell
cd C:\MapleOCR
.\run_v193_full_inventory.ps1
```

The real run writes detailed output to:

```text
C:\MapleOCR\Results
```

and keeps these convenience files in the MapleOCR root:

```text
C:\MapleOCR\mapleupload.txt
C:\MapleOCR\Output_v193_check.zip
```

A previous `BIS_stats.zip` is removed after a new real Optical Character Recognition run because it may describe an older inventory state.

After importing the new `mapleupload.txt` into the optimizer and exporting a fresh `mapleexport.txt`, run:

```powershell
cd C:\MapleOCR
.\build_BIS_stats_v193.ps1
```

The resulting `BIS_stats.zip` contains the same-run Best in Slot source files, including:

- `mapleexport.txt`
- `lock_status.txt`
- `maplelocked.txt`
- `import_review_easyocr_v193.csv`
- `screenshot_manifest_v193.txt`
- `screenshot_capture_order_v193.csv`
- `RUN_ID.txt`

## Validation baseline

The v193 release candidate was validated on a mixed-level inventory containing:

- 305 bag equipment screenshots
- 14 Equipped screenshots
- 319 total screenshots
- 319 trusted equipment rows
- 0 review items

The final Best in Slot builder was also validated on that run and successfully created `BIS_stats.zip`.

## Directory cleanup

Double-click:

```text
MapleOCR_Directory_Cleaner.bat
```

Enter the latest build number when prompted. Old versioned and helper files are moved into a timestamped folder under `backups`; they are not permanently deleted.
