$ErrorActionPreference = 'Stop'

$Root = 'C:\MapleOCR'
$Script = Join-Path $Root 'maple_batch_importer_easyocr_v180.py'
$Screenshots = Join-Path $Root 'screenshots'
$Export = Join-Path $Root 'mapleexport.txt'

Set-Location $Root

if (Test-Path (Join-Path $Root '.venv\Scripts\Activate.ps1')) {
    . (Join-Path $Root '.venv\Scripts\Activate.ps1')
}

python $Script $Screenshots $Export --full-inventory

Write-Host ''
Write-Host 'Real run finished.'
Write-Host 'Import: C:\MapleOCR\mapleupload.txt'
Write-Host 'Locks:  C:\MapleOCR\maplelocked.txt'
