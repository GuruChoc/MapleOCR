# Install / Setup

## One-time folder setup

Expected root folder:

```powershell
C:\MapleOCR
```

Expected screenshot folders:

```powershell
C:\MapleOCR\screenshots
C:\MapleOCR\screenshots\Equipped
```

## Python virtual environment

```powershell
cd C:\MapleOCR
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Baseline optimiser export

Place the latest optimiser export here:

```powershell
C:\MapleOCR\mapleexport.txt
```

## Dry-run

```powershell
cd C:\MapleOCR
.\run_v180_full_inventory_dry_run.ps1
```

## Real run

Only run after dry-run output has been checked.

```powershell
cd C:\MapleOCR
.\run_v180_full_inventory.ps1
```
