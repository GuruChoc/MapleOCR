# MapleOCR

Windows helper workflow for MapleStory: Idle RPG equipment OCR.

## Current baseline

**v191**

v191 includes:

- Equipped screenshots rebuilding the Basic Preset
- fresh bag inventory OCR
- white-first foreground stat reading
- comparison/background bleed filtering
- split/comma-formatted whole-number reconstruction
- targeted main Attack fragment reconstruction
- zero-rounding parser policy
- Defense Penetration parsing
- conservative stat min/max validation
- lock-state snapshots from the same screenshot batch
- screenshot capture timestamp/order tracking for BIS LOCK/UNLOCK sorting
- automatic Arena, Colosseum, HP, MP and Chapter Boss preset rebuilding
- generated detail files under `C:\MapleOCR\Results`
- `mapleupload.txt` compatibility copy in `C:\MapleOCR`
- automatic `BIS_stats.zip` containing matching BIS source files from the same run
- automatic `Output_v191_check.zip` creation after the normal real run
- reusable popup-based MapleOCR directory cleaner

Personal screenshots, optimiser exports, OCR results and generated ZIPs should not be committed.

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
.\run_v191_full_inventory_dry_run.ps1
```

Real run + automatic check ZIP:

```powershell
cd C:\MapleOCR
.\run_v191_full_inventory.ps1
```

The real run writes detailed output to:

```text
C:\MapleOCR\Results
```

and keeps these convenience files in the MapleOCR root:

```text
C:\MapleOCR\mapleupload.txt
C:\MapleOCR\BIS_stats.zip
C:\MapleOCR\Output_v191_check.zip
```

`BIS_stats.zip` contains the matching files from the same OCR run:

- `mapleexport.txt`
- `lock_status.txt`
- `maplelocked.txt`
- `import_review_easyocr_v191.csv`

## Directory cleanup

Double-click:

```text
MapleOCR_Directory_Cleaner.bat
```

Enter the latest build number when prompted. Old versioned/helper files are moved into a timestamped folder under `backups`; they are not permanently deleted.
