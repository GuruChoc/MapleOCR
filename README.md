# MapleOCR

MapleOCR turns MapleStory: Idle RPG equipment screenshots into structured equipment/inventory data for the optimiser and BIS report workflow.

## v194 workflow

1. Capture bag screenshots in `C:\MapleOCR\screenshots`.
2. Capture currently equipped Basic Preset screenshots in `C:\MapleOCR\screenshots\Equipped`.
3. Run MapleOCR v194.
4. Import `C:\MapleOCR\mapleupload.txt` into the optimiser.
5. Export fresh optimiser data to `C:\MapleOCR\mapleexport.txt`.
6. Run `\.\build_BIS_stats_v194.ps1`.
7. Upload `C:\MapleOCR\BIS_stats.zip` to the BIS report workflow.

## v194 BIS report authority

v194 adds `Results\bis_report_authority_v194.csv`, generated from the same OCR RUN_ID.

This file is the authority for:
- first-substat validation: use screenshot/OCR row order
- LOCK/UNLOCK working order: use BAG `source_capture_order` ascending

Do not infer first-substat order from optimiser export order or lock-status serialization.

## Validated v194 test

- 305 bag screenshots
- 14 Equipped screenshots
- 319 trusted items
- 0 review items
- 319 BIS authority rows
- BAG capture order 1–305 with no gaps/duplicates
- first-substat authority 319/319 with 0 mismatches
- final `BIS_stats.zip` successfully built after a fresh optimiser import/export

## Main files

- `maple_batch_importer_easyocr_v194.py`
- `build_bis_stats_v194.py`
- `build_BIS_stats_v194.ps1`
- `run_v194_full_inventory.ps1`
- `run_v194_full_inventory_dry_run.ps1`
- `run_v194_full_inventory_and_zip.ps1`
- `open_v194_results.ps1`
- `MapleOCR_Directory_Cleaner.bat`

Personal screenshots, exports, results, and generated ZIP files should not be committed to the repository.
