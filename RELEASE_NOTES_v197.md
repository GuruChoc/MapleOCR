# MapleOCR v197

v197 improves Equipped Star Force badge detection while preserving the fail-closed safety introduced in v196.

## Why v197 was needed

v196 correctly refused to write `mapleupload.txt` when it could not confidently read the Star Force badge on a new Equipped Shoulder screenshot:

- File: `IU5Ma6SzjU.png`
- Item: Wise Royal Pauldron
- Visible Star Force: 17

The screenshot itself was clear, but the original single-pass badge OCR returned no plausible digits.

## What changed

- Keeps the fixed Equipped Star Force badge region introduced in v196.
- Runs multiple conservative OCR preprocessing variants over that same badge region.
- Adds tighter right-side badge passes to reduce interference from the yellow star icon.
- Prefers complete two-digit Star Force reads.
- Requires agreement when competing candidates appear.
- Keeps fail-closed behaviour for ambiguous reads.
- Single-digit Star Force values require repeated observations.
- Retains the v196 Star Force authority sync for `equipmentStarForceBySlot`.
- Retains the v195 split-Attack reconstruction fix.
- Retains the v194/v195 BIS authority rules:
  - first substat comes from screenshot/OCR row order
  - LOCK/UNLOCK order follows BAG `source_capture_order`

## Validated v197 run

- MapleOCR root: `C:\MapleProjects\MapleOCR`
- 242 bag screenshots
- 14 Equipped screenshots
- 256 total trusted items
- 0 review items
- all 14 Equipped Star Force values read correctly
- previously failing Shoulder read correctly as Star Force 17
- Shoulder 26,520 survived optimiser round-trip unchanged
- known Belt 26,785 / 7,973 / 11.5% / 12% remained unchanged
- final `BIS_stats.zip` successfully built and validated
- 256 BIS authority rows
- 0 first-substat mismatches
- BAG capture order 1–242 with no gaps
- Equipped capture order 1–14 with no gaps

## Current workflow

1. Run MapleOCR v197 from the Maple Toolbox GUI or PowerShell.
2. Import `C:\MapleProjects\MapleOCR\mapleupload.txt` into the optimiser.
3. Export a fresh `mapleexport.txt` back to `C:\MapleProjects\MapleOCR`.
4. Run `.\build_BIS_stats_v197.ps1`.
5. Use `C:\MapleProjects\MapleOCR\BIS_stats.zip` for the BIS report workflow.

## Main files

- `maple_batch_importer_easyocr_v197.py`
- `build_bis_stats_v197.py`
- `build_BIS_stats_v197.ps1`
- `run_v197_full_inventory.ps1`
- `run_v197_full_inventory_dry_run.ps1`
- `run_v197_full_inventory_and_zip.ps1`
- `open_v197_results.ps1`
- `MapleOCR_Directory_Cleaner.bat`

Personal screenshots, optimiser exports, results and generated ZIPs should not be committed to the repository.
