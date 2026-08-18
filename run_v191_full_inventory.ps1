Set-Location C:\MapleOCR
.\.venv\Scripts\Activate.ps1

Write-Host ""
Write-Host "Running MapleOCR v191 REAL run..."
Write-Host ""

python C:\MapleOCR\maple_batch_importer_easyocr_v191.py `
    C:\MapleOCR\screenshots `
    C:\MapleOCR\mapleexport.txt `
    --full-inventory `
    --output-dir C:\MapleOCR\Results

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "OCR run failed. Results ZIP was not created."
    exit $LASTEXITCODE
}

$results = "C:\MapleOCR\Results"
$zip = "C:\MapleOCR\Output_v191_check.zip"

Write-Host ""
Write-Host "Creating fresh results ZIP..."
Write-Host ""

if (-not (Test-Path -LiteralPath $results)) {
    Write-Host "ERROR: Results folder does not exist: $results"
    exit 1
}

if (Test-Path -LiteralPath $zip) {
    Remove-Item -LiteralPath $zip -Force
}

$files = Get-ChildItem -LiteralPath $results -Force

if (-not $files) {
    Write-Host "ERROR: No files found in Results."
    exit 1
}

Compress-Archive `
    -Path $files.FullName `
    -DestinationPath $zip `
    -CompressionLevel Optimal `
    -Force

if (-not (Test-Path -LiteralPath $zip)) {
    Write-Host "ERROR: ZIP creation failed."
    exit 1
}

Write-Host ""
Write-Host "DONE"
Write-Host "Results:      C:\MapleOCR\Results"
Write-Host "Upload JSON:  C:\MapleOCR\mapleupload.txt"
Write-Host "BIS ZIP:      C:\MapleOCR\BIS_stats.zip"
Write-Host "Check ZIP:    C:\MapleOCR\Output_v191_check.zip"
Write-Host ""
