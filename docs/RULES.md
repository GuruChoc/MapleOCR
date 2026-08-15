# MapleOCR Rules

## Source of truth

Use the latest OCR screenshot batch as the equipment source of truth.

`mapleexport.txt` is used as the optimiser baseline for settings, preset names, and schema shape only. Old equipment records should not be preserved.

## Equipped / Basic Preset

`C:\MapleOCR\screenshots\Equipped` contains currently worn gear.

Those 14 screenshots must populate:

```text
equipmentPresets[0] / Basic Preset
equippedItemsBySlot
equipmentBaseStats
```

## No stat scaling

Write values exactly as read from the screenshot.

Do not reverse-scale attack values.
Do not scale percentage substats.

## Slot main-stat rows

After `On-Equip Effect`, read exactly 3 fixed main stat rows by slot, then treat later rows as substats.

```text
Hat / Top:                 Attack, Max HP, Defense
Bottom / Gloves:           Attack, Max HP, Accuracy
Ring / Eye / Earring /
Necklace / Face:           Attack, Max HP, Main Stat
Cape / Shoulder:           Attack, Max HP, Evasion
Belt / Shoes:              Attack, Max HP, Max MP
```

## Lock snapshot

`maplelocked.txt` is a snapshot of locked equipment from the same screenshot batch.

`lock_status.txt` includes every trusted item and its lock status.

Locked detection should fail closed. If the lock icon/status is unclear, mark it `unclear` in `lock_status.txt` and do not place it in `maplelocked.txt`.

## Arena / Colosseum

Arena and Colosseum use the same build.

Priority:

```text
Evasion first
Accuracy second
Damage only after survivability/accuracy needs are met
```

Accuracy protection: avoid a tiny Evasion gain if it drops projected Arena Accuracy below the rough target. If an Accuracy item is within about 2 Evasion of the best Evasion item, prefer or keep the Accuracy item.

## HP / MP

HP and MP sets are short-use stat/potion-helper sets, not combat sets.

HP chooses highest total Max HP per slot.
MP prefers Max MP percentage, falling back to flat Max MP only when needed.

## Breakthrough

Do not build Breakthrough in OCR. Leave Chapter Breakthrough to the optimiser/manual workflow.
