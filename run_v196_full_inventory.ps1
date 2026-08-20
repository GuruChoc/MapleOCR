Set-Location C:\MapleProjects\MapleOCR
.\.venv\Scripts\Activate.ps1

Write-Host ""
Write-Host "Running MapleOCR v196 REAL run..."
Write-Host ""

python C:\MapleProjects\MapleOCR\maple_batch_importer_easyocr_v196.py `
    C:\MapleProjects\MapleOCR\screenshots `
    C:\MapleProjects\MapleOCR\mapleexport.txt `
    --full-inventory `
    --output-dir C:\MapleProjects\MapleOCR\Results

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "OCR returned exit code $LASTEXITCODE."
    Write-Host "Check C:\MapleProjects\MapleOCR\Output_v196_check.zip for review details."
}

Write-Host ""
Write-Host "DONE"
Write-Host "Results:      C:\MapleProjects\MapleOCR\Results"
Write-Host "Upload JSON:  C:\MapleProjects\MapleOCR\mapleupload.txt"
Write-Host "Check ZIP:    C:\MapleProjects\MapleOCR\Output_v196_check.zip"
Write-Host ""
Write-Host "BIS_stats.zip is intentionally NOT created yet."
Write-Host "After optimiser import + fresh export, run:"
Write-Host "  .\build_BIS_stats_v196.ps1"
Write-Host ""
