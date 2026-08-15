@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM MapleOCR cleanup helper
REM Moves old versioned files/folders below v180 into a timestamped holding folder.
REM It does NOT delete anything.

set "ROOT=C:\MapleOCR"

if not exist "%ROOT%" (
  echo ERROR: %ROOT% does not exist.
  pause
  exit /b 1
)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"
set "HOLD=%ROOT%\_old_versions_below_v180_%STAMP%"

mkdir "%HOLD%" >nul 2>nul

set "REPORT=%HOLD%\cleanup_report.txt"
echo MapleOCR cleanup report > "%REPORT%"
echo Started: %DATE% %TIME% >> "%REPORT%"
echo Root: %ROOT% >> "%REPORT%"
echo Holding folder: %HOLD% >> "%REPORT%"
echo. >> "%REPORT%"

echo.
echo MapleOCR cleanup
echo ----------------
echo Moving old v001-v179 files/folders into:
echo %HOLD%
echo.
echo Nothing will be deleted.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = 'C:\MapleOCR';" ^
  "$hold = '%HOLD%';" ^
  "$report = '%REPORT%';" ^
  "$keepNames = @('.venv','screenshots','Output','mapleexport.txt','mapleupload.txt','maplelocked.txt','lock_status.txt');" ^
  "$items = Get-ChildItem -LiteralPath $root -Force | Where-Object { $keepNames -notcontains $_.Name -and $_.FullName -ne $hold };" ^
  "foreach ($item in $items) {" ^
  "  $name = $item.Name;" ^
  "  $move = $false;" ^
  "  if ($name -match '(?i)v(\d{1,3})') { if ([int]$matches[1] -lt 180) { $move = $true } }" ^
  "  elseif ($name -match '(?i)^Output_v(\d{1,3})(?:\b|\(|\.|_)') { if ([int]$matches[1] -lt 180) { $move = $true } }" ^
  "  elseif ($name -match '(?i)^MapleOCR_v(\d{1,3})') { if ([int]$matches[1] -lt 180) { $move = $true } }" ^
  "  elseif ($name -match '(?i)^run_v(\d{1,3})') { if ([int]$matches[1] -lt 180) { $move = $true } }" ^
  "  elseif ($name -match '(?i)^maple_batch_importer_easyocr_v(\d{1,3})') { if ([int]$matches[1] -lt 180) { $move = $true } }" ^
  "  if ($move) {" ^
  "    $dest = Join-Path $hold $name;" ^
  "    Add-Content -LiteralPath $report -Value ('MOVE: ' + $item.FullName + ' -> ' + $dest);" ^
  "    Move-Item -LiteralPath $item.FullName -Destination $dest -Force;" ^
  "  } else {" ^
  "    Add-Content -LiteralPath $report -Value ('KEEP: ' + $item.FullName);" ^
  "  }" ^
  "}"

echo.
echo Cleanup pass complete.
echo.
echo Report:
echo %REPORT%
echo.
echo Please inspect the holding folder before manually deleting anything.
echo.
pause
endlocal
