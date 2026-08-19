Set-Location C:\MapleOCR
.\.venv\Scripts\Activate.ps1

Write-Host ""
Write-Host "Running MapleOCR v195 REAL run..."
Write-Host ""

python C:\MapleOCR\maple_batch_importer_easyocr_v195.py `
    C:\MapleOCR\screenshots `
    C:\MapleOCR\mapleexport.txt `
    --full-inventory `
    --output-dir C:\MapleOCR\Results

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "OCR returned exit code $LASTEXITCODE."
    Write-Host "Check C:\MapleOCR\Output_v195_check.zip for review details."
}

Write-Host ""
Write-Host "DONE"
Write-Host "Results:      C:\MapleOCR\Results"
Write-Host "Upload JSON:  C:\MapleOCR\mapleupload.txt"
Write-Host "Check ZIP:    C:\MapleOCR\Output_v195_check.zip"
Write-Host ""
Write-Host "BIS_stats.zip is intentionally NOT created yet."
Write-Host "After optimiser import + fresh export, run:"
Write-Host "  .\build_BIS_stats_v195.ps1"
Write-Host ""
