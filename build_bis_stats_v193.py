#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import Counter
import json
import re
import sys
import zipfile
from pathlib import Path

VERSION = "v193"

def fail(msg: str, code: int = 1) -> int:
    print("")
    print("BIS_stats.zip NOT created.")
    print(msg)
    return code

def read_run_id_from_lock_status(path: Path) -> str:
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"#\s*RUN_ID:\s*(\S+)", line)
        if m:
            return m.group(1)
    raise ValueError("RUN_ID not found in lock_status.txt")

STAT_NAME_TO_TYPE = {
    "Attack": "attack",
    "Max HP": "max-hp",
    "Max MP": "max-mp",
    "Defense": "defense",
    "Accuracy": "accuracy",
    "Evasion": "evasion",
    "Main Stat": "main-stat",
    "Main Stat %": "main-stat-percent",
    "Critical Rate": "crit-rate",
    "Critical Damage": "crit-damage",
    "Attack Speed": "attack-speed",
    "Normal Monster Damage": "normal-damage",
    "Boss Monster Damage": "boss-damage",
    "Damage": "damage",
    "Final Damage": "final-damage",
    "Min Damage Multiplier": "min-damage-ratio",
    "Max Damage Multiplier": "max-damage-ratio",
    "Basic Attack Damage": "basic-attack-damage",
    "Defense Penetration": "defense-penetration",
    "1st Job Skill Lv.": "skill-level-1",
    "2nd Job Skill Lv.": "skill-level-2",
    "3rd Job Skill Lv.": "skill-level-3",
    "4th Job Skill Lv.": "skill-level-4",
}

def norm_num(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return value
    return int(f) if f.is_integer() else round(f, 6)


def read_review_run_ids(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = csv.DictReader(f)
        if "run_id" not in (rows.fieldnames or []):
            raise ValueError(f"{path.name} has no run_id column")
        return {
            str(r.get("run_id", "")).strip()
            for r in rows
            if str(r.get("run_id", "")).strip()
        }


def parse_lock_substats(raw: str) -> tuple[tuple[str, object], ...]:
    out = []
    for chunk in [x.strip() for x in raw.split(";") if x.strip()]:
        matched = False
        for label in sorted(STAT_NAME_TO_TYPE, key=len, reverse=True):
            prefix = label + " "
            if chunk.startswith(prefix):
                value_text = chunk[len(prefix):].strip().replace(",", "")
                try:
                    value = norm_num(float(value_text))
                except ValueError:
                    value = value_text
                out.append((STAT_NAME_TO_TYPE[label], value))
                matched = True
                break
        if not matched:
            out.append((chunk, None))
    return tuple(sorted(out))

def read_lock_inventory(path: Path):
    """Read every OCR item as a physical-item signature.

    Internal equipment IDs are NOT used for stale-export validation because the
    optimiser can legitimately reassign them during import/export.

    Signature = slot + visible Attack + ordered substats.
    Counter semantics preserve duplicate identical items.
    """
    rows = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue

        _status, slot, iid_raw, name, source, filename, substats = parts[:7]

        try:
            iid = int(iid_raw)
        except ValueError:
            continue

        m = re.match(r"\s*(\d[\d,]*)", name)
        if not m:
            raise ValueError(f"Could not read Attack from lock entry: {line}")
        attack = int(m.group(1).replace(",", ""))

        # Keep substat order exactly as recorded by OCR. This is stronger than
        # sorting because first/second/etc. line position is part of the item.
        stats = []
        for chunk in [x.strip() for x in substats.split(";") if x.strip()]:
            matched = False
            for label in sorted(STAT_NAME_TO_TYPE, key=len, reverse=True):
                prefix = label + " "
                if chunk.startswith(prefix):
                    value_text = chunk[len(prefix):].strip().replace(",", "")
                    try:
                        value = norm_num(float(value_text))
                    except ValueError:
                        value = value_text
                    stats.append((STAT_NAME_TO_TYPE[label], value))
                    matched = True
                    break
            if not matched:
                stats.append((chunk, None))

        signature = (slot, attack, tuple(stats))
        rows.append({
            "id": iid,
            "slot": slot,
            "source": source,
            "filename": filename,
            "signature": signature,
        })

    if not rows:
        raise ValueError("No equipment rows found in lock_status.txt")

    return rows

def export_item_signature(slot: str, item: dict):
    """Physical-item signature matching the OCR lock-status representation."""
    try:
        attack = int(item.get("attack"))
    except (TypeError, ValueError):
        attack = -1

    stats = []
    raw_stats = item.get("stats")
    if isinstance(raw_stats, list):
        for stat in raw_stats:
            if not isinstance(stat, dict):
                continue
            stype = stat.get("type")
            if not stype:
                continue
            stats.append((str(stype), norm_num(stat.get("value"))))

    # Preserve optimiser stat order. Do not sort.
    return (str(slot), attack, tuple(stats))

def read_export_inventory(path: Path):
    """Read every optimiser inventory item from comparisonItemsBySlot."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    by_slot = data.get("comparisonItemsBySlot")
    if not isinstance(by_slot, dict):
        raise ValueError("mapleexport.txt has no comparisonItemsBySlot inventory")

    rows = []
    for slot, items in by_slot.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                iid = int(item.get("id"))
            except (TypeError, ValueError):
                iid = -1
            rows.append({
                "id": iid,
                "slot": str(slot),
                "signature": export_item_signature(str(slot), item),
            })

    if not rows:
        raise ValueError("mapleexport.txt contains no inventory equipment")

    return rows

def fmt_signature(sig) -> str:
    slot, attack, stats = sig
    if stats:
        stat_text = ", ".join(f"{t}={v}" for t, v in stats)
    else:
        stat_text = "no substats"
    return f"{slot} ATK {attack} [{stat_text}]"


def item_signature(item: dict):
    try:
        attack = int(item.get("attack"))
    except (TypeError, ValueError):
        attack = -1
    stats = []
    raw_stats = item.get("stats")
    if isinstance(raw_stats, list):
        for stat in raw_stats:
            if not isinstance(stat, dict):
                continue
            stype = stat.get("type")
            if not stype:
                continue
            stats.append((str(stype), norm_num(stat.get("value"))))
    return attack, tuple(stats)

def find_basic_index(data: dict) -> int:
    names = data.get("equipmentPresetNames") or []
    for i, name in enumerate(names):
        if str(name).strip().lower() in {"basic preset", "basic", "preset 1"}:
            return i
    raise ValueError("Basic Preset not found in mapleexport.txt")

def equipment_base_from_item(item: dict):
    return {
        "mainAttack": int(item.get("attack") or 0),
        "mainMainStat": int(item.get("mainStat") or 0),
        "mainDefense": int(item.get("defense") or 0),
        "mainAccuracy": int(item.get("accuracy") or 0),
        "mainEvasion": int(item.get("evasion") or 0),
        "subOptions": json.loads(json.dumps(item.get("stats") or [])),
        "subAttack": 0,
    }

def signature_compatible(ocr_sig, export_sig):
    """True when export item is compatible with the RUN_ID-bound OCR record.

    lock_status.txt is reliable for slot + main Attack, but its serialized
    substat list can omit the first substat on some Equipped rows. Therefore
    the OCR stats are treated as an ordered subsequence of the export stats,
    not as an exact full-stat equality.

    This remains strict on slot (handled by caller) and main Attack.
    """
    if not ocr_sig or not export_sig:
        return False

    # signatures are (slot, attack, ordered_stats) in this builder.
    try:
        ocr_slot, ocr_attack, ocr_stats = ocr_sig
        exp_slot, exp_attack, exp_stats = export_sig
    except Exception:
        return False

    if ocr_slot != exp_slot or ocr_attack != exp_attack:
        return False

    if not ocr_stats:
        return True

    # ordered subsequence: allows lock_status to omit one or more stat lines,
    # while refusing re-ordered or contradictory values.
    j = 0
    for stat in exp_stats:
        if j < len(ocr_stats) and stat == ocr_stats[j]:
            j += 1
    return j == len(ocr_stats)


def find_compatible_candidates(slot: str, desired_sig, items):
    out = []
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        sig = export_item_signature(slot, item)
        if signature_compatible(desired_sig, sig):
            out.append(item)
    return out


def normalize_basic_from_lock_status(export_data: dict, ocr_rows: list):
    """Normalize Basic from the current RUN_ID's lock_status.txt.

    lock_status is generated from the exact OCR run and is already tied to
    RUN_ID. This avoids relying on root mapleupload.txt, which can be stale or
    independently overwritten.

    A slot is repaired only when the exact physical OCR signature exists in
    either the exported equipped item or comparison inventory.
    """
    data = json.loads(json.dumps(export_data))
    export_equipped = data.get("equippedItemsBySlot")
    comparison = data.get("comparisonItemsBySlot")
    if not isinstance(export_equipped, dict):
        raise ValueError("mapleexport.txt has no equippedItemsBySlot")
    if not isinstance(comparison, dict):
        raise ValueError("mapleexport.txt has no comparisonItemsBySlot")

    presets = data.get("equipmentPresets")
    if not isinstance(presets, list):
        raise ValueError("mapleexport.txt has no equipmentPresets")
    basic_idx = find_basic_index(data)
    while len(presets) <= basic_idx:
        presets.append({})
    if not isinstance(presets[basic_idx], dict):
        presets[basic_idx] = {}

    bases = data.get("equipmentBaseStats")
    if not isinstance(bases, dict):
        bases = {}
        data["equipmentBaseStats"] = bases

    equipped_ocr = [r for r in ocr_rows if r.get("source") == "equipped"]
    by_slot = {r["slot"]: r for r in equipped_ocr}

    # Physical BAG signatures from this exact RUN_ID. If an optimiser Basic slot
    # has drifted to a different item that is nevertheless confirmed in the BAG,
    # repairing Basic must not make that displaced physical item disappear from
    # the inventory. We preserve it in comparisonItemsBySlot.
    bag_signatures_by_slot = {}
    for r in ocr_rows:
        if r.get("source") != "bag":
            continue
        bag_signatures_by_slot.setdefault(r["slot"], []).append(r["signature"])

    corrected = []
    preserved_displaced = []

    for slot, row in by_slot.items():
        desired_sig = row["signature"]
        current = export_equipped.get(slot)

        current_sig = export_item_signature(slot, current) if isinstance(current, dict) else None

        # lock_status may omit the first substat, so require exact slot + Attack
        # and require every OCR-recorded substat to appear in export order.
        if current_sig and signature_compatible(desired_sig, current_sig):
            chosen = current
        else:
            candidates = find_compatible_candidates(
                slot, desired_sig, comparison.get(slot)
            )

            if not candidates:
                got = current_sig
                raise ValueError(
                    f"Cannot repair Basic {slot}: OCR wants {fmt_signature(desired_sig)}, "
                    f"export equipped has {fmt_signature(got) if got else 'missing'}, "
                    f"and no compatible physical match exists in comparisonItemsBySlot[{slot!r}]"
                )

            # Prefer an exact full signature if available; otherwise choose the
            # richest compatible candidate. Main Attack and all OCR-recorded
            # ordered substats are already guaranteed to match.
            exact = [
                item for item in candidates
                if export_item_signature(slot, item) == desired_sig
            ]
            pool = exact if exact else candidates
            chosen = max(pool, key=lambda x: (len(x.get("stats") or []), len(x.keys())))

            # If the old exported Equipped item is a confirmed BAG item from the
            # same OCR run, keep it in comparisonItemsBySlot before replacing the
            # Basic slot. This is the confirmed Bottom 21465 -> 18135 behaviour:
            # 21465 remains a real bag item, while 18135 is the current equipped
            # Basic item.
            if current_sig:
                bag_sigs = bag_signatures_by_slot.get(slot, [])
                if current_sig in bag_sigs:
                    arr = comparison.setdefault(slot, [])
                    if isinstance(arr, list):
                        already = any(
                            isinstance(x, dict) and export_item_signature(slot, x) == current_sig
                            for x in arr
                        )
                        if not already:
                            arr.append(json.loads(json.dumps(current)))
                            preserved_displaced.append(slot)

            export_equipped[slot] = json.loads(json.dumps(chosen))
            corrected.append(slot)

        presets[basic_idx][slot] = int(chosen.get("id"))
        bases[slot] = equipment_base_from_item(chosen)

    if isinstance(export_equipped.get("hat"), dict):
        data["equippedItem"] = json.loads(json.dumps(export_equipped["hat"]))

    return data, corrected, preserved_displaced


def normalize_basic_from_current_upload(export_data: dict, upload_data: dict):
    """Correct optimiser Basic/equipped drift using the exact current OCR upload.

    The optimiser can retain one stale equipped slot after import/export even
    though the newly imported physical item exists in comparisonItemsBySlot.
    We do NOT invent an item. A mismatched slot is corrected only when the exact
    OCR physical signature exists in the freshly exported inventory.

    Returns (normalized_export, corrected_slots).
    """
    data = json.loads(json.dumps(export_data))
    desired_equipped = upload_data.get("equippedItemsBySlot")
    if not isinstance(desired_equipped, dict) or not desired_equipped:
        raise ValueError("Current Results/mapleupload.txt has no equippedItemsBySlot")

    export_equipped = data.get("equippedItemsBySlot")
    comparison = data.get("comparisonItemsBySlot")
    if not isinstance(export_equipped, dict):
        raise ValueError("mapleexport.txt has no equippedItemsBySlot")
    if not isinstance(comparison, dict):
        raise ValueError("mapleexport.txt has no comparisonItemsBySlot")

    bases = data.get("equipmentBaseStats")
    if not isinstance(bases, dict):
        bases = {}
        data["equipmentBaseStats"] = bases

    upload_bases = upload_data.get("equipmentBaseStats") or {}
    presets = data.get("equipmentPresets")
    if not isinstance(presets, list):
        raise ValueError("mapleexport.txt has no equipmentPresets")
    basic_idx = find_basic_index(data)
    while len(presets) <= basic_idx:
        presets.append({})
    if not isinstance(presets[basic_idx], dict):
        presets[basic_idx] = {}

    corrected = []

    for slot, desired in desired_equipped.items():
        if not isinstance(desired, dict):
            continue

        desired_sig = item_signature(desired)
        current = export_equipped.get(slot)

        # If the optimiser already exported the correct physical item, keep its
        # optimiser-assigned ID but still synchronize Basic to that ID.
        if isinstance(current, dict) and item_signature(current) == desired_sig:
            chosen = current
        else:
            candidates = []
            for item in comparison.get(slot, []) if isinstance(comparison.get(slot), list) else []:
                if isinstance(item, dict) and item_signature(item) == desired_sig:
                    candidates.append(item)

            if not candidates:
                got = item_signature(current) if isinstance(current, dict) else None
                raise ValueError(
                    f"Cannot repair Basic {slot}: OCR wants {desired_sig}, "
                    f"export equipped has {got}, and no exact physical match "
                    f"exists in comparisonItemsBySlot[{slot!r}]"
                )

            # Prefer the richest candidate when duplicate identical physical
            # rows exist (e.g. one may carry build helper fields).
            chosen = max(candidates, key=lambda x: len(x.keys()))
            export_equipped[slot] = json.loads(json.dumps(chosen))
            corrected.append(slot)

        chosen_id = int(chosen.get("id"))
        presets[basic_idx][slot] = chosen_id

        # Keep equipmentBaseStats aligned with the current OCR Basic snapshot.
        if isinstance(upload_bases, dict) and isinstance(upload_bases.get(slot), dict):
            bases[slot] = json.loads(json.dumps(upload_bases[slot]))

    # Keep top-level equippedItem coherent. The optimiser currently uses Hat as
    # the top-level equippedItem in this workflow; preserve that convention if
    # Hat exists.
    if isinstance(export_equipped.get("hat"), dict):
        data["equippedItem"] = json.loads(json.dumps(export_equipped["hat"]))

    return data, corrected


def main() -> int:
    base = Path(r"C:\MapleOCR")
    results = base / "Results"

    mapleexport = base / "mapleexport.txt"
    lock_status = results / "lock_status.txt"
    maplelocked = results / "maplelocked.txt"
    review_csv = results / f"import_review_easyocr_{VERSION}.csv"
    manifest = results / f"screenshot_manifest_{VERSION}.txt"
    capture_csv = results / f"screenshot_capture_order_{VERSION}.csv"
    run_id_file = results / "RUN_ID.txt"
    out_zip = base / "BIS_stats.zip"

    required = [mapleexport, lock_status, maplelocked, review_csv, manifest, capture_csv, run_id_file]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        return fail("Missing required file(s):\n  " + "\n  ".join(missing))

    try:
        lock_run_id = read_run_id_from_lock_status(lock_status)
        review_run_ids = read_review_run_ids(review_csv)
        if review_run_ids != {lock_run_id}:
            return fail(
                f"RUN_ID mismatch: lock_status.txt={lock_run_id}, "
                f"{review_csv.name}={sorted(review_run_ids)}"
            )

        run_id_text = run_id_file.read_text(encoding="utf-8-sig")
        if f"RUN_ID: {lock_run_id}" not in run_id_text:
            return fail("RUN_ID.txt does not match lock_status.txt")

        manifest_text = manifest.read_text(encoding="utf-8-sig")
        if f"RUN_ID: {lock_run_id}" not in manifest_text:
            return fail(f"{manifest.name} does not match lock_status.txt RUN_ID")

        # Parse the RUN_ID-bound OCR inventory first, then normalize the
        # optimiser Basic/equipped state from those exact physical signatures.
        # This deliberately does NOT use root mapleupload.txt.
        ocr_rows = read_lock_inventory(lock_status)
        export_data_raw = json.loads(mapleexport.read_text(encoding="utf-8-sig"))
        export_data, corrected_basic_slots, preserved_displaced_slots = normalize_basic_from_lock_status(
            export_data_raw, ocr_rows
        )

        normalized_export = results / f"mapleexport_BIS_normalized_{VERSION}.txt"
        normalized_export.write_text(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        export_rows = read_export_inventory(normalized_export)

        bag_ocr = [x for x in ocr_rows if x["source"] == "bag"]
        equipped_ocr = [x for x in ocr_rows if x["source"] == "equipped"]

        # 1) Equipped screenshots are authoritative for the current Basic set.
        #    Validate those first against equippedItemsBySlot.
        export_data = json.loads(normalized_export.read_text(encoding="utf-8-sig"))
        equipped_by_slot = export_data.get("equippedItemsBySlot")
        if not isinstance(equipped_by_slot, dict):
            return fail("mapleexport.txt has no equippedItemsBySlot")

        equipped_expected = {x["slot"]: x for x in equipped_ocr}
        equipped_mismatches = []

        for slot, expected in equipped_expected.items():
            item = equipped_by_slot.get(slot)
            if not isinstance(item, dict):
                equipped_mismatches.append(
                    f"{slot}: missing from equippedItemsBySlot"
                )
                continue

            actual_sig = export_item_signature(slot, item)
            if not signature_compatible(expected["signature"], actual_sig):
                equipped_mismatches.append(
                    f"{slot}: OCR {fmt_signature(expected['signature'])} "
                    f"!= export {fmt_signature(actual_sig)}"
                )

        if equipped_mismatches:
            lines = [
                "STALE / MISMATCHED mapleexport.txt detected.",
                f"Current OCR RUN_ID: {lock_run_id}",
                "",
                f"Equipped/Basic mismatches ({len(equipped_mismatches)}):",
            ]
            lines.extend(f"  {x}" for x in equipped_mismatches[:20])
            lines += [
                "",
                "Import the current mapleupload.txt into the optimiser,",
                "re-export mapleexport.txt, then run the BIS builder again.",
            ]
            return fail("\n".join(lines))

        # 2) Every BAG screenshot item must exist somewhere in the optimiser's
        #    current physical equipment state.
        #
        # Important optimiser behaviour confirmed from the user's fresh export:
        # an equipped item may either:
        #   - remain duplicated in comparisonItemsBySlot, OR
        #   - be removed from comparisonItemsBySlot and exist only in
        #     equippedItemsBySlot (the 21465 Bottom does exactly this).
        #
        # Therefore BAG validation uses comparisonItemsBySlot PLUS the current
        # equippedItemsBySlot signatures as an availability pool.
        bag_counter = Counter(x["signature"] for x in bag_ocr)
        comparison_counter = Counter(x["signature"] for x in export_rows)

        equipped_export_signatures = []
        for slot, item in equipped_by_slot.items():
            if isinstance(item, dict):
                equipped_export_signatures.append(export_item_signature(slot, item))
        equipped_counter = Counter(equipped_export_signatures)

        available_counter = comparison_counter + equipped_counter
        missing_bag = bag_counter - available_counter

        if missing_bag:
            lines = [
                "STALE / MISMATCHED mapleexport.txt detected.",
                f"Current OCR RUN_ID: {lock_run_id}",
                f"OCR BAG rows: {len(bag_ocr)}",
                f"comparisonItemsBySlot rows: {len(export_rows)}",
                f"equippedItemsBySlot rows: {len(equipped_export_signatures)}",
                "",
                f"Missing BAG physical item signatures ({sum(missing_bag.values())}):",
            ]
            for sig, count in list(missing_bag.items())[:20]:
                lines.append(f"  {count} x {fmt_signature(sig)}")
            lines += [
                "",
                "Import the current mapleupload.txt into the optimiser,",
                "re-export mapleexport.txt, then run the BIS builder again.",
            ]
            return fail("\n".join(lines))

        # Surplus comparison/cache rows are tolerated. They are not proof of a
        # stale export because the optimiser can retain duplicate cached rows.
        surplus = comparison_counter - bag_counter

        members = [
            (normalized_export, "mapleexport.txt"),
            (lock_status, "lock_status.txt"),
            (maplelocked, "maplelocked.txt"),
            (review_csv, review_csv.name),
            (manifest, manifest.name),
            (capture_csv, capture_csv.name),
            (run_id_file, "RUN_ID.txt"),
        ]

        tmp = out_zip.with_suffix(".zip.tmp")
        if tmp.exists():
            tmp.unlink()
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for source, arcname in members:
                zf.write(source, arcname=arcname)
        tmp.replace(out_zip)

        pending_root = base / f"BIS_stats_PENDING_{VERSION}.txt"
        if pending_root.exists():
            pending_root.unlink()

        print("")
        print("BIS_stats.zip created successfully.")
        if corrected_basic_slots:
            print("Normalized optimiser Basic slot(s): " + ", ".join(corrected_basic_slots))
        else:
            print("Optimizer Basic already matched current OCR Equipped snapshot.")
        if preserved_displaced_slots:
            print("Preserved displaced BAG item(s): " + ", ".join(preserved_displaced_slots))
        print(f"RUN_ID: {lock_run_id}")
        print(f"Validated BAG items: {len(bag_ocr)}")
        print(f"Validated Equipped/Basic items: {len(equipped_ocr)}")
        print("Validation: BAG items found across comparison/equipped state + exact equippedItemsBySlot match")
        if surplus:
            print(f"Note: optimiser inventory contains {sum(surplus.values())} cached/duplicate surplus row(s); tolerated.")
        print(f"Created: {out_zip}")
        return 0

    except Exception as exc:
        return fail(f"Validation error: {exc}")

if __name__ == "__main__":
    raise SystemExit(main())
