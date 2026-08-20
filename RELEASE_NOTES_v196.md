# MapleOCR v196

v196 fixes a Star Force metadata sync problem that could cause the optimiser to re-scale equipment that had already been upgraded in-game.

## What changed

- Preserves the validated v195 OCR behaviour, including the 22,927 Attack reconstruction fix.
- Reads the Star Force badge from every `screenshots\Equipped` screenshot.
- Uses the Equipped screenshot Star Force value as the authority for `equipmentStarForceBySlot`.
- Prevents stale optimiser Star Force metadata from re-scaling already-visible equipment stats.
- Adds `Results\star_force_sync_v196.txt` so each slot shows:
  - screenshot Star Force
  - previous optimiser Star Force
  - `OK` or `UPDATED`
- Fails closed if an Equipped Star Force value cannot be read reliably.
- Keeps the v194/v195 BIS authority rules:
  - first substat comes from screenshot/OCR row order
  - LOCK/UNLOCK order follows BAG `source_capture_order`

## Confirmed bug

A real Belt showed in-game:

- Main Attack: 26,785
- Sub Attack: 7,973
- Boss Monster Damage: 11.5%
- Critical Rate: 12%
- Star Force: 17

The optimiser still had Belt Star Force 15, so the visible 17-star values were boosted again.

v196 synchronises the screenshot Star Force before producing `mapleupload.txt`.

## Validated v196 run

- MapleOCR root: `C:\MapleProjects\MapleOCR`
- 212 bag screenshots
- 14 Equipped screenshots
- 226 total trusted items
- 0 review items
- all 14 Equipped Star Force badges read correctly
- Belt 26,785 survived the full:
  `screenshot -> OCR -> mapleupload.txt -> optimiser -> mapleexport.txt`
  round-trip unchanged
- final `BIS_stats.zip` successfully built and validated
- BIS report workflow passed

## Current workflow

1. Run MapleOCR v196 from the GUI or directly.
2. Import `C:\MapleProjects\MapleOCR\mapleupload.txt` into the optimiser.
3. Export a fresh `mapleexport.txt` back to `C:\MapleProjects\MapleOCR`.
4. Run:
   `.\build_BIS_stats_v196.ps1`
5. Use `C:\MapleProjects\MapleOCR\BIS_stats.zip` for the BIS report workflow.

## Main files

- `maple_batch_importer_easyocr_v196.py`
- `build_bis_stats_v196.py`
- `build_BIS_stats_v196.ps1`
- `run_v196_full_inventory.ps1`
- `run_v196_full_inventory_dry_run.ps1`
- `run_v196_full_inventory_and_zip.ps1`
- `open_v196_results.ps1`
- `MapleOCR_Directory_Cleaner.bat`

Personal screenshots, optimiser exports, results and generated ZIPs should not be committed to the repository.
