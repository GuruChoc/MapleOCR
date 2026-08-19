MapleOCR v194

MapleOCR v194 hardens the BIS report hand-off while preserving the validated v193 OCR behaviour.

Highlights
- Adds a same-run BIS report authority file generated directly from OCR results.
- Records first-substat authority from actual screenshot/OCR row order.
- Records BAG source_capture_order as the authoritative LOCK/UNLOCK working order.
- Packages BIS report provenance into BIS_stats.zip.
- Validates authority rows against the current RUN_ID and physical OCR items before allowing BIS_stats.zip to be created.
- Keeps v193 mixed-level equipment handling, white-first OCR logic, no rounding/scaling, Equipped-as-Basic behaviour, and conservative optimiser reconciliation.

Validated workflow
- 305 bag screenshots
- 14 Equipped screenshots
- 319 total trusted items
- 0 review/rejected items
- 319 BIS authority rows
- BAG source_capture_order validated 1 through 305 with no gaps or duplicates
- First-substat authority validated 319/319 with 0 mismatches
- Final BIS_stats.zip successfully created and validated after fresh optimiser import/export

New v194 BIS authority files
- Results\bis_report_authority_v194.csv
- Results\BIS_REPORT_AUTHORITY_v194.txt

BIS workflow
1. Run MapleOCR v194.
2. Upload C:\MapleOCR\mapleupload.txt to the optimiser.
3. Export fresh optimiser data to C:\MapleOCR\mapleexport.txt.
4. Run .\build_BIS_stats_v194.ps1
5. Upload C:\MapleOCR\BIS_stats.zip to the BISMIRPG report workflow.

Public release asset
- MapleOCR_v194_bundle.zip
