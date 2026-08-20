# MapleOCR

MapleOCR turns MapleStory: Idle RPG equipment screenshots into structured equipment/inventory data for the optimiser and BIS report workflow.

## Current location

`C:\MapleProjects\MapleOCR`

MapleOCR can be launched through the Maple Toolbox GUI or run directly from PowerShell.

## v196 workflow

1. Capture bag screenshots in `C:\MapleProjects\MapleOCR\screenshots`.
2. Capture the 14 currently equipped Basic Preset items in `C:\MapleProjects\MapleOCR\screenshots\Equipped`.
3. Run MapleOCR v196.
4. Import `C:\MapleProjects\MapleOCR\mapleupload.txt` into the optimiser.
5. Export fresh optimiser data to `C:\MapleProjects\MapleOCR\mapleexport.txt`.
6. Run `.\build_BIS_stats_v196.ps1`.
7. Use `C:\MapleProjects\MapleOCR\BIS_stats.zip` for the BIS report workflow.

## v196 Star Force sync

v196 reads the Star Force badge from each Equipped screenshot and makes those screenshot values authoritative for `equipmentStarForceBySlot`.

This prevents stale optimiser Star Force metadata from applying a second equipment boost after an in-game upgrade.

The run creates:

`Results\star_force_sync_v196.txt`

showing the screenshot Star Force, previous optimiser Star Force and whether each slot was already correct or was updated.

## v195 Attack reconstruction retained

v196 retains the v195 fix for split Attack OCR such as:

`22,5 + 927 -> 22,927`

without restoring a global minimum Attack rule.

## BIS report authority

The v194/v195 authority rules remain in place:

- first-substat validation uses screenshot/OCR row order
- LOCK/UNLOCK working order uses BAG `source_capture_order` ascending

## Validated v196 release

- 212 bag screenshots
- 14 Equipped screenshots
- 226 trusted items
- 0 review items
- all 14 Equipped Star Force values validated
- Belt 26,785 / 7,973 / 11.5% / 12% survived the optimiser round-trip unchanged
- final `BIS_stats.zip` successfully built and validated
- BIS report workflow passed

## Main files

- `maple_batch_importer_easyocr_v196.py`
- `build_bis_stats_v196.py`
- `build_BIS_stats_v196.ps1`
- `run_v196_full_inventory.ps1`
- `run_v196_full_inventory_dry_run.ps1`
- `run_v196_full_inventory_and_zip.ps1`
- `open_v196_results.ps1`
- `MapleOCR_Directory_Cleaner.bat`

Personal screenshots, optimiser exports, results and generated ZIPs should not be committed.
