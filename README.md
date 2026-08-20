# MapleOCR

MapleOCR turns MapleStory: Idle RPG equipment screenshots into structured equipment/inventory data for the optimiser and BIS report workflow.

## Current location

`C:\MapleProjects\MapleOCR`

MapleOCR can be launched through the Maple Toolbox GUI or run directly from PowerShell.

## v197 workflow

1. Capture bag screenshots in `C:\MapleProjects\MapleOCR\screenshots`.
2. Capture the 14 currently equipped Basic Preset items in `C:\MapleProjects\MapleOCR\screenshots\Equipped`.
3. Run MapleOCR v197.
4. Import `C:\MapleProjects\MapleOCR\mapleupload.txt` into the optimiser.
5. Export fresh optimiser data to `C:\MapleProjects\MapleOCR\mapleexport.txt`.
6. Run `.\build_BIS_stats_v197.ps1`.
7. Use `C:\MapleProjects\MapleOCR\BIS_stats.zip` for the BIS report workflow.

## v197 Star Force badge detection

v197 keeps the v196 Equipped Star Force authority sync and improves badge recognition by using several conservative OCR preprocessing passes over the same fixed badge area.

This fixes a confirmed clear Shoulder screenshot that v196 correctly refused to trust.

Ambiguous Star Force reads still fail closed rather than guessing.

## v196 Star Force authority retained

Equipped screenshot Star Force values remain authoritative for `equipmentStarForceBySlot`.

This prevents stale optimiser Star Force metadata from applying a second equipment boost after an in-game upgrade.

## v195 Attack reconstruction retained

The split Attack reconstruction fix remains in place, for example:

`22,5 + 927 -> 22,927`

without using a global minimum Attack rule.

## BIS report authority

The existing authority rules remain unchanged:

- first-substat validation uses screenshot/OCR row order
- LOCK/UNLOCK working order uses BAG `source_capture_order` ascending

## Validated v197 release

- 242 bag screenshots
- 14 Equipped screenshots
- 256 trusted items
- 0 review items
- all 14 Equipped Star Force values validated
- previously failing Shoulder read correctly as Star Force 17
- optimiser round-trip passed
- final `BIS_stats.zip` successfully built and validated
- 256 BIS authority rows
- 0 first-substat mismatches

## Main files

- `maple_batch_importer_easyocr_v197.py`
- `build_bis_stats_v197.py`
- `build_BIS_stats_v197.ps1`
- `run_v197_full_inventory.ps1`
- `run_v197_full_inventory_dry_run.ps1`
- `run_v197_full_inventory_and_zip.ps1`
- `open_v197_results.ps1`
- `MapleOCR_Directory_Cleaner.bat`

Personal screenshots, optimiser exports, results and generated ZIPs should not be committed.
