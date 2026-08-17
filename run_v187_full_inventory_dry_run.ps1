Set-Location C:\MapleOCR
.\.venv\Scripts\Activate.ps1

python C:\MapleOCR\maple_batch_importer_easyocr_v187.py `
    C:\MapleOCR\screenshots `
    C:\MapleOCR\mapleexport.txt `
    --dry-run `
    --full-inventory
