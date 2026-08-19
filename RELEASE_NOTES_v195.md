MapleOCR v195

MapleOCR v195 is a targeted OCR reliability release built on the validated v194 BIS authority workflow.

What changed
------------
- Preserves the validated v194 OCR, BIS authority, capture-order and BIS_stats.zip workflow.
- Fixes a confirmed main Attack-row split-fragment failure caused by an unrelated non-numeric/background OCR token appearing between the Attack label and numeric fragments.
- Confirmed failure pattern:
    Attack | Speler | 22,5 | 927 -180
  v194 could fall through and trust 927.
  v195 ignores the non-numeric background token and applies the existing split reconstruction:
    22,5 + 927 -> 22,927
- The fix is deliberately narrow. It does NOT restore a global minimum Attack rule, so legitimate low-level equipment remains supported.
- Existing white-first foreground rules, structural reconstruction bounds, no-rounding/no-scaling behaviour, same-run BIS authority and capture-order logic remain unchanged.

Confirmed regression target
---------------------------
Hat: Necro Magician Hat
T3, Lv.108
Attack: 22,927
Max HP: 115,110
Defense: 3,100
Substats:
- Critical Rate 11.2%
- Max MP 26.2%
- 2nd Job Skill Lv. 8

Validated release run
---------------------
- 305 bag screenshots
- 14 Equipped screenshots
- 319 total trusted items
- 0 review/rejected items
- Hat 5PNjsN7Hh1.png correctly reconstructed as Attack 22,927
- 319 BIS authority rows
- BAG source_capture_order validated 1 through 305 with no gaps or duplicates
- Equipped source_capture_order validated 1 through 14
- First-substat authority validated 319/319 with 0 mismatches
- Final BIS_stats.zip successfully created and validated after fresh optimiser import/export
- BIS report confirmed working with the v195 BIS_stats.zip

BIS workflow
------------
1. Run MapleOCR v195.
2. Upload C:\MapleOCR\mapleupload.txt to the optimiser.
3. Export fresh optimiser data to C:\MapleOCR\mapleexport.txt.
4. Run:
   .\build_BIS_stats_v195.ps1
5. Upload C:\MapleOCR\BIS_stats.zip to the BISMIRPG report workflow.
