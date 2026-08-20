Set-Location C:\MapleProjects\MapleOCR
.\.venv\Scripts\Activate.ps1

python C:\MapleProjects\MapleOCR\maple_batch_importer_easyocr_v196.py `
    C:\MapleProjects\MapleOCR\screenshots `
    C:\MapleProjects\MapleOCR\mapleexport.txt `
    --dry-run `
    --full-inventory `
    --output-dir C:\MapleProjects\MapleOCR\Results
