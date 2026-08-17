Set-Location C:\MapleOCR

$zip = "C:\MapleOCR\Output_v187_check.zip"
if (Test-Path $zip) {
    Remove-Item $zip -Force
}

Compress-Archive `
    -Path C:\MapleOCR\Output\* `
    -DestinationPath $zip `
    -CompressionLevel Optimal `
    -Force

Write-Host ""
Write-Host "Created: $zip"
