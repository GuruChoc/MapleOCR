$results = "C:\MapleOCR\Results"
if (-not (Test-Path $results)) {
    New-Item -ItemType Directory -Path $results -Force | Out-Null
}
Start-Process explorer.exe $results
