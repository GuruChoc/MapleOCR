Set-Location C:\MapleOCR

$results = "C:\MapleOCR\Results"
$zip = "C:\MapleOCR\Output_v191_check.zip"

if (-not (Test-Path $results)) {
    Write-Host "Results folder does not exist: $results"
    exit 1
}

if (Test-Path $zip) {
    Remove-Item $zip -Force
}

$files = Get-ChildItem -LiteralPath $results -Force
if (-not $files) {
    Write-Host "No result files found to zip."
    exit 1
}

Compress-Archive `
    -Path $files.FullName `
    -DestinationPath $zip `
    -CompressionLevel Optimal `
    -Force

Write-Host ""
Write-Host "Created: $zip"
Write-Host "BIS handoff: C:\MapleOCR\BIS_stats.zip"
