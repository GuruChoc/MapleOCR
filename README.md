# MapleOCR

MapleOCR turns MapleStory: Idle RPG equipment screenshots into structured equipment/inventory data for the optimiser and BIS report workflow.

## v195 workflow

1. Capture bag screenshots in `C:\MapleOCR\screenshots`.
2. Capture currently equipped Basic Preset screenshots in `C:\MapleOCR\screenshots\Equipped`.
3. Run MapleOCR v195.
4. Import `C:\MapleOCR\mapleupload.txt` into the optimiser.
5. Export fresh optimiser data to `C:\MapleOCR\mapleexport.txt`.
6. Run `.\build_BIS_stats_v195.ps1`.
7. Upload `C:\MapleOCR\BIS_stats.zip` to the BISMIRPG report workflow.

## v195 OCR fix

v195 fixes a confirmed main Attack split-fragment failure where a non-numeric/background OCR token could appear between the `Attack` label and the actual number fragments.

Confirmed example:

`Attack | Speler | 22,5 | 927 -180`

v195 ignores the unrelated text token and reconstructs:

`22,5 + 927 -> 22,927`

This is deliberately targeted. MapleOCR does **not** use a global minimum Attack rule, so legitimate lower-level equipment remains supported.

## BIS report authority

The v194 authority rules remain unchanged in v195.

`Results\bis_report_authority_v195.csv` is generated from the same OCR RUN_ID and is the authority for:

- first-substat validation: screenshot/OCR row order
- LOCK/UNLOCK working order: BAG `source_capture_order` ascending

Do not infer first-substat order from optimiser export order or lock-status serialization.

## Validated v195 release

- 305 bag screenshots
- 14 Equipped screenshots
- 319 trusted items
- 0 review items
- 319 BIS authority rows
- BAG capture order 1–305 with no gaps/duplicates
- Equipped capture order 1–14
- first-substat authority 319/319 with 0 mismatches
- confirmed Hat Attack reconstruction: 22,927
- final `BIS_stats.zip` successfully built and validated
- BIS report confirmed working

## Main files

- `maple_batch_importer_easyocr_v195.py`
- `build_bis_stats_v195.py`
- `build_BIS_stats_v195.ps1`
- `run_v195_full_inventory.ps1`
- `run_v195_full_inventory_dry_run.ps1`
- `run_v195_full_inventory_and_zip.ps1`
- `open_v195_results.ps1`
- `MapleOCR_Directory_Cleaner.bat`

Personal screenshots, exports, results, and generated ZIP files should not be committed to the repository.
