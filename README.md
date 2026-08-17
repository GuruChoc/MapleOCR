# MapleOCR

Windows helper workflow for MapleStory: Idle RPG equipment OCR.

## Current baseline

**v187**

v187 includes:
- Equipped screenshots rebuilding Basic Preset
- bag inventory OCR
- fixed lock-button colour detection
- white-first foreground stat reading
- comparison/background bleed filtering
- zero-rounding parser policy
- explicit Defense Penetration parsing
- whole-number reconstruction for comma-formatted values
- conservative stat min/max OCR validation
- automatic Arena, Colosseum, HP, MP and Chapter Boss preset rebuilding

Personal screenshots and generated optimiser/OCR output should not be committed.

## Run

Dry run:

```powershell
cd C:\MapleOCR
.\run_v187_full_inventory_dry_run.ps1
```

Real run:

```powershell
cd C:\MapleOCR
.\run_v187_full_inventory.ps1
```

Create a check ZIP:

```powershell
cd C:\MapleOCR
.\zip_v187_check_output.ps1
```

