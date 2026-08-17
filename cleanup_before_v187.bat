@echo off
setlocal EnableExtensions EnableDelayedExpansion
title MapleOCR cleanup - remove versions before v187

cd /d C:\MapleOCR

echo.
echo ============================================================
echo  MapleOCR CLEANUP - REMOVE VERSIONED FILES BEFORE v187
echo ============================================================
echo.
echo This will remove OLD VERSIONED MapleOCR files where the
echo filename/folder contains v### with a version lower than 187.
echo.
echo It targets old:
echo   - .py importer scripts
echo   - .ps1 scripts
echo   - .bat files
echo   - .zip files
echo   - old versioned folders such as v180check / v184check
echo.
echo It will NOT remove:
echo   - v187 files
echo   - screenshots
echo   - screenshots\Equipped
echo   - mapleexport.txt
echo   - current Output folder
echo   - .venv
echo   - unversioned files
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$root='C:\MapleOCR';" ^
"$keep=187;" ^
"$targets = Get-ChildItem -LiteralPath $root -Force | Where-Object {" ^
"  $_.Name -match '(?i)v(\d{3})' -and [int]$Matches[1] -lt $keep" ^
"};" ^
"if(-not $targets){ Write-Host 'Nothing older than v187 found.' -ForegroundColor Green; exit 0 };" ^
"Write-Host 'The following will be DELETED:' -ForegroundColor Yellow;" ^
"$targets | Sort-Object Name | ForEach-Object { Write-Host ('  ' + $_.FullName) };" ^
"Write-Host '';"

echo.
choice /C YN /N /M "Delete everything listed above? [Y/N]: "
if errorlevel 2 (
    echo.
    echo Cancelled. Nothing was deleted.
    pause
    exit /b 0
)

echo.
echo Deleting old versioned files/folders...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$root='C:\MapleOCR';" ^
"$keep=187;" ^
"$targets = Get-ChildItem -LiteralPath $root -Force | Where-Object {" ^
"  $_.Name -match '(?i)v(\d{3})' -and [int]$Matches[1] -lt $keep" ^
"};" ^
"$targets | ForEach-Object {" ^
"  try {" ^
"    Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop;" ^
"    Write-Host ('DELETED: ' + $_.Name) -ForegroundColor DarkGray" ^
"  } catch {" ^
"    Write-Host ('FAILED:  ' + $_.FullName + ' -- ' + $_.Exception.Message) -ForegroundColor Red" ^
"  }" ^
"}"

echo.
echo ------------------------------------------------------------
echo Cleaning OLD .bat files that do not contain v187...
echo ------------------------------------------------------------

for %%F in ("C:\MapleOCR\*.bat") do (
    if /I not "%%~nxF"=="cleanup_before_v187.bat" (
        echo %%~nxF | findstr /I /C:"v187" >nul
        if errorlevel 1 (
            echo Deleting old BAT: %%~nxF
            del /F /Q "%%~fF" >nul 2>&1
        )
    )
)

echo.
echo ============================================================
echo  CLEANUP COMPLETE
echo ============================================================
echo.
echo Remaining versioned MapleOCR files:
powershell -NoProfile -Command ^
"Get-ChildItem -LiteralPath 'C:\MapleOCR' -Force | Where-Object { $_.Name -match '(?i)v\d{3}' } | Sort-Object Name | Select-Object -ExpandProperty Name"

echo.
pause
