$ErrorActionPreference = 'Stop'

$Root = 'C:\MapleOCR'
$Script = Join-Path $Root 'maple_batch_importer_easyocr_v180.py'
$Screenshots = Join-Path $Root 'screenshots'
$Export = Join-Path $Root 'mapleexport.txt'

Set-Location $Root

if (Test-Path (Join-Path $Root '.venv\Scripts\Activate.ps1')) {
    . (Join-Path $Root '.venv\Scripts\Activate.ps1')
}

python $Script $Screenshots $Export --dry-run --full-inventory

Write-Host ''
Write-Host 'Dry-run finished. Upload/check C:\MapleOCR\Output_v180.zip before real import.'
