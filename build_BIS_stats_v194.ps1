Set-Location C:\MapleOCR
.\.venv\Scripts\Activate.ps1

python C:\MapleOCR\build_bis_stats_v194.py

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Ready to upload:"
Write-Host "  C:\MapleOCR\BIS_stats.zip"
