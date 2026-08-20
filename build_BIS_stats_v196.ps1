Set-Location C:\MapleProjects\MapleOCR
.\.venv\Scripts\Activate.ps1

python C:\MapleProjects\MapleOCR\build_bis_stats_v196.py

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Ready to upload:"
Write-Host "  C:\MapleProjects\MapleOCR\BIS_stats.zip"
