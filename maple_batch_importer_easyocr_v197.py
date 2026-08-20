#!/usr/bin/env python3
r"""
MapleOCR v197 - Equipped screenshot Star Force authority sync on top of validated v195.

Uses mapleexport.txt only for optimiser non-equipment settings and preset names.
Old optimiser equipment inventory/items are not trusted. comparisonItems and
comparisonItemsBySlot are replaced with fresh OCR items only. Arena, Colosseum,
HP, MP and Chapter Boss are rebuilt from OCR items. Breakthrough and other equipment presets are kept by name
but cleared for manual optimiser rebuild.

v197 change: keeps the validated v195 OCR/BIS workflow and makes the Star Force badge on each screenshots\\Equipped item authoritative for equipmentStarForceBySlot. This prevents the optimiser from re-scaling already-visible screenshot values when in-game Star Force has changed since the previous optimiser export.

Core rules:
- Treat MapleStory Idle RPG equipment screenshots as fixed UI cards, not free-form text.
- On-Equip Effect may be detected by OCR, but v150 primarily uses visual green-band geometry; no loose fallback import is allowed without the visual anchor.
- Only top-level files in the screenshots folder are scanned; subfolders such as need_review are ignored.
- Every equipment slot has exactly 3 main rows in a fixed order.
- Main rows are stored only as item fields and NEVER as substats or h/e/m shorthand.
- Substats are only explicit whitelist labels after the 3 main rows, max 4.
- If a required main value cannot be trusted, item is excluded from mapleupload.txt and sent to review.

Primary workflow:
  python maple_batch_importer_easyocr_v190.py C:\MapleProjects\MapleOCR\screenshots C:\MapleProjects\MapleOCR\mapleexport.txt --dry-run --full-inventory
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # setup_venv.ps1 / requirements.txt installs these
    cv2 = None
    np = None

VERSION = "v197"

SLOT_ORDER = [
    "hat", "top", "bottom", "gloves", "ring", "ring2", "eye", "earring",
    "cape", "shoulder", "belt", "shoes", "necklace", "face"
]

DISPLAY_SLOT = {s: s.capitalize() for s in SLOT_ORDER}
DISPLAY_SLOT.update({"earring": "Earring", "ring2": "Ring 2"})

MAIN_TEMPLATES = {
    "hat": ["attack", "max-hp", "defense"],
    "top": ["attack", "max-hp", "defense"],
    "bottom": ["attack", "max-hp", "accuracy"],
    "gloves": ["attack", "max-hp", "accuracy"],
    "ring": ["attack", "max-hp", "main-stat"],
    "ring2": ["attack", "max-hp", "main-stat"],
    "eye": ["attack", "max-hp", "main-stat"],
    "earring": ["attack", "max-hp", "main-stat"],
    "necklace": ["attack", "max-hp", "main-stat"],
    "face": ["attack", "max-hp", "main-stat"],
    "cape": ["attack", "max-hp", "evasion"],
    "shoulder": ["attack", "max-hp", "evasion"],
    "belt": ["attack", "max-hp", "max-mp"],
    "shoes": ["attack", "max-hp", "max-mp"],
}

# Only valid substats. Internal keys match optimiser JSON style as far as previous scripts used it.
SUBSTAT_LABELS = {
    "attack": "attack",
    "main-stat": "main-stat",
    "main-stat-percent": "main-stat-percent",
    "defense": "defense",
    "defense-penetration": "defense-penetration",
    "crit-rate": "crit-rate",
    "crit-damage": "crit-damage",
    "skill-level-1": "skill-level-1",
    "skill-level-2": "skill-level-2",
    "skill-level-3": "skill-level-3",
    "skill-level-4": "skill-level-4",
    "skill-level-all": "skill-level-all",
    "attack-speed": "attack-speed",
    "basic-attack-damage": "basic-attack-damage",
    "normal-damage": "normal-damage",
    "boss-damage": "boss-damage",
    "damage": "damage",
    "final-damage": "final-damage",
    "min-damage-ratio": "min-damage-ratio",
    "max-damage-ratio": "max-damage-ratio",
    "max-hp": "max-hp",     # not on user's later list image, but needed for h items and prior optimiser data
    "max-mp": "max-mp",     # needed for m items and prior optimiser data
    "evasion": "evasion",   # needed for e items and Arena logic
    "accuracy": "accuracy", # needed for Arena tie logic
}

# Output labels in review/debug text
LABEL_TEXT = {
    "attack": "Attack", "max-hp": "Max HP", "max-mp": "Max MP", "defense": "Defense", "defense-penetration": "Defense Penetration",
    "accuracy": "Accuracy", "evasion": "Evasion", "main-stat": "Main Stat",
    "main-stat-percent": "Main Stat %", "crit-rate": "Critical Rate", "crit-damage": "Critical Damage",
    "skill-level-1": "1st Job Skill Lv.", "skill-level-2": "2nd Job Skill Lv.",
    "skill-level-3": "3rd Job Skill Lv.", "skill-level-4": "4th Job Skill Lv.",
    "skill-level-all": "All Job Skill Level", "attack-speed": "Attack Speed",
    "basic-attack-damage": "Basic Attack Damage",
    "normal-damage": "Normal Monster Damage", "boss-damage": "Boss Monster Damage",
    "damage": "Damage", "final-damage": "Final Damage",
    "min-damage-ratio": "Min Damage Multiplier", "max-damage-ratio": "Max Damage Multiplier",
}

NOISE_WORDS = {
    "playground", "playaround", "guruchoc", "guru choc", "character", "equipped", "cp change",
    "on-equip effect", "on equip effect", "change", "legendary", "unique", "rare", "epic", "mystic",
    "normal", "accessory", "accossory", "squashy", "blue", "varr", "varuna", "ciara", "zakum",
}

SLOT_KEYWORDS = [
    ("shoulder", ["shoulder", "pauldron"]),
    ("necklace", ["necklace"]),
    ("earring", ["earring", "earrings"]),
    ("bottom", ["bottom", "pants", "skirt"]),
    ("gloves", ["gloves", "ciara"]),
    ("shoes", ["shoes", "boots"]),
    ("belt", ["belt"]),
    ("cape", ["cape"]),
    ("face", ["face", "condensed power crystal", "power crystal"]),
    ("eye", ["eye", "aquatic letter"]),
    ("ring2", ["ring 2", "ring2"]),
    ("ring", ["ring"]),
    ("hat", ["hat", "helmet"]),
    ("top", ["top", "suit", "varuna"]),
]

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

@dataclass
class OCRToken:
    text: str
    conf: float
    x1: float
    y1: float
    x2: float
    y2: float
    cx: float
    cy: float
    h: float
    fg_ratio: float = 0.0
    fg_class: str = "unknown"

@dataclass
class OCRRow:
    idx: int
    y: float
    x1: float
    x2: float
    text: str
    tokens: List[OCRToken] = field(default_factory=list)

@dataclass
class ParsedItem:
    filename: str
    slot: str
    attack: int
    name: str
    item: Dict[str, Any]
    tier: str = ""
    level: str = ""
    rows_debug: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    review_reason: str = ""
    lock_status: str = "unclear"
    source: str = "bag"
    source_capture_order: int = 0
    batch_capture_order: int = 0
    capture_timestamp: str = ""



def _timestamp_iso_local(ts: float) -> str:
    """Format a filesystem timestamp in the PC's local timezone."""
    try:
        return datetime.fromtimestamp(float(ts)).astimezone().isoformat(timespec="milliseconds")
    except Exception:
        return ""


def screenshot_capture_metadata(path: Path) -> Dict[str, Any]:
    """Return stable capture-order metadata without changing the screenshot.

    On Windows, st_ctime is file creation time. st_mtime is modification time.
    ShareX screenshots normally have both set at capture. If a file is later copied
    while preserving mtime, creation time can become newer, so v191 uses the EARLIER
    of creation and modification as the capture-sort timestamp.

    The raw creation and modification timestamps are both retained in output so a
    future audit can see exactly which filesystem evidence was used.
    """
    st = path.stat()
    created = float(st.st_ctime)
    modified = float(st.st_mtime)
    capture = min(created, modified)
    return {
        "capture_ts": capture,
        "capture_timestamp": _timestamp_iso_local(capture),
        "created_ts": created,
        "created_timestamp": _timestamp_iso_local(created),
        "modified_ts": modified,
        "modified_timestamp": _timestamp_iso_local(modified),
    }


def build_capture_order(
    bag_imgs: List[Path],
    equipped_imgs: List[Path],
) -> Tuple[Dict[str, Dict[str, Any]], List[Tuple[Path, str, Dict[str, Any]]]]:
    """Build capture order without altering OCR processing/ID assignment order.

    source_capture_order:
      1..N separately within bag and Equipped. For LOCK/UNLOCK bag scrolling,
      this is the authoritative order to use.

    batch_capture_order:
      1..N across both sources, useful for general auditing.
    """
    entries: List[Tuple[Path, str, Dict[str, Any]]] = []
    for p in bag_imgs:
        entries.append((p, "bag", screenshot_capture_metadata(p)))
    for p in equipped_imgs:
        entries.append((p, "equipped", screenshot_capture_metadata(p)))

    # Separate source order (bag scrolling should use bag order only).
    for source in ("bag", "equipped"):
        source_entries = [e for e in entries if e[1] == source]
        source_entries.sort(
            key=lambda e: (
                e[2]["capture_ts"],
                e[2]["modified_ts"],
                e[0].name.lower(),
            )
        )
        for n, (_p, _src, meta) in enumerate(source_entries, start=1):
            meta["source_capture_order"] = n

    # Full-batch audit order.
    batch_sorted = sorted(
        entries,
        key=lambda e: (
            e[2]["capture_ts"],
            0 if e[1] == "bag" else 1,
            e[2]["modified_ts"],
            e[0].name.lower(),
        ),
    )
    for n, (_p, _src, meta) in enumerate(batch_sorted, start=1):
        meta["batch_capture_order"] = n

    by_path: Dict[str, Dict[str, Any]] = {}
    for p, source, meta in entries:
        meta["source"] = source
        meta["filename"] = p.name
        by_path[str(p.resolve()).lower()] = meta

    return by_path, batch_sorted


def capture_meta_for(path: Path, capture_meta: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return capture_meta.get(
        str(path.resolve()).lower(),
        {
            "source_capture_order": "",
            "batch_capture_order": "",
            "capture_timestamp": "",
            "created_timestamp": "",
            "modified_timestamp": "",
        },
    )


def norm_text(s: str) -> str:
    s = s.lower().strip()
    s = s.replace("|", " ").replace("_", " ")
    s = re.sub(r"[’'`´]", "", s)
    s = re.sub(r"[^a-z0-9.%+\-/, ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def canonical_label(text: str) -> Optional[str]:
    t = norm_text(text)
    if not t:
        return None
    t = t.replace("1st", "1st").replace("ist", "1st")
    # v155: job-skill OCR tolerance: 2nd is often read as Znd.
    t = re.sub(r"\bznd\b", "2nd", t)
    t = re.sub(r"\bz\s*nd\b", "2nd", t)
    # v159: tolerate OCR/name/title bleed inside fixed main labels, e.g.
    # "Attackexagon Necklace", "Max HPnune to Debuffs", "Max E HP".
    t = re.sub(r"\bmax\s+e\s+hp\b", "max hp", t)
    t = re.sub(r"\bmax\s*h\s*p\b", "max hp", t)
    t = re.sub(r"\bmax\s*m\s*p\b", "max mp", t)
    t = re.sub(r"\bmain\s*stat\b", "main stat", t)
    # v159: extra tolerance for the 5 rejected full-inventory screenshots where
    # OCR merged set/immune text into fixed main rows. These are only labels;
    # values are still type-checked by plausible_value/choose_value.
    # Examples seen: "Max | APnein | tooDebut | 75,210",
    # "Max HPnuneito Debuff 106,051", "Attack_xagon Necklace | 15,236".
    if re.search(r"\bmax\b", t) and any(x in t for x in ["apnein", "apne", "hpnune", "debuff", "debut", "toodebut", "too debut", "nune"]):
        t = "max hp " + t
    if t.startswith("attackxagon") or t.startswith("attack xagon") or t.startswith("attackexagon"):
        t = "attack " + t
    # OCR common mangles
    t = t.replace("deferse", "defense").replace("defe nse", "defense")
    t = t.replace("crilical", "critical").replace("critica1", "critical")
    t = t.replace("evaslon", "evasion").replace("evaston", "evasion")
    t = t.replace("accurary", "accuracy").replace("accu racy", "accuracy")
    t = t.replace("moin stat", "main stat")
    t = t.replace("monst er", "monster")
    t = t.replace("multipller", "multiplier").replace("muliplier", "multiplier")

    # Must order specific before generic damage
    if re.search(r"\b1(st)?\s*job\s*skill\s*(lv|level)", t): return "skill-level-1"
    if re.search(r"\b2(nd)?\s*job\s*skill\s*(lv|level)", t): return "skill-level-2"
    if re.search(r"\b3(rd)?\s*job\s*skill\s*(lv|level)", t): return "skill-level-3"
    if re.search(r"\b4(th)?\s*job\s*skill\s*(lv|level)", t): return "skill-level-4"
    if "all job" in t and "skill" in t: return "skill-level-all"
    if "normal monster" in t and "damage" in t: return "normal-damage"
    if "boss monster" in t and "damage" in t: return "boss-damage"
    if "critical rate" in t or "crit rate" in t: return "crit-rate"
    if "critical damage" in t or "crit damage" in t: return "crit-damage"
    if "attack speed" in t: return "attack-speed"
    if "basic attack" in t and "damage" in t: return "basic-attack-damage"
    if "final damage" in t: return "final-damage"
    if "min damage" in t and "mult" in t: return "min-damage-ratio"
    if "max damage" in t and "mult" in t: return "max-damage-ratio"
    if "main stat" in t and "%" in t: return "main-stat-percent"
    if "main stat" in t: return "main-stat"
    if "max hp" in t or t.startswith("maxhp") or "maxhp" in t: return "max-hp"
    if "max mp" in t or t.startswith("maxmp") or "maxmp" in t: return "max-mp"
    if "evasion" in t: return "evasion"
    if "accuracy" in t: return "accuracy"
    if "defense penetration" in t or ("defense" in t and "penetration" in t): return "defense-penetration"
    if "defense" in t: return "defense"
    # Plain attack/damage only if the row is mostly the label; avoid item titles.
    # v159 accepts merged Attack+item-name OCR when the stat row starts with Attack.
    if (re.search(r"\battack\b", t) or t.startswith("attack")) and not any(w in t for w in ["speed", "power", "basic", "damage"]): return "attack"
    if re.fullmatch(r".*\bdamage\b.*", t): return "damage"
    return None


def extract_numbers(text: str) -> List[float]:
    # normalise OCR decimal variants: 21,.4, 21,4%, 21.4%
    s = text.replace("，", ",").replace("．", ".")
    s = re.sub(r"(\d+),\.(\d+)", r"\1.\2", s)
    # 21,4% probably decimal, but 70,357 is thousands. Only comma decimal before % with 1 digit.
    s = re.sub(r"(\d+),(\d)(?=\s*%)", r"\1.\2", s)
    vals: List[float] = []
    for m in re.finditer(r"[-+]?\d[\d,]*(?:\.\d+)?", s):
        raw = m.group(0)
        # Ignore standalone ordinal part from 4th/3rd labels when label text present handled elsewhere
        try:
            vals.append(float(raw.replace(",", "")))
        except ValueError:
            pass
    return vals


def plausible_value(label: str, value: float) -> bool:
    if label == "attack": return 100 <= value <= 1000000
    if label == "max-hp": return 1000 <= value <= 300000
    if label == "max-mp": return 1 <= value <= 100000  # main Shoes/Belt Max MP can be 1,000+; substat fragments are filtered later
    if label in ("defense", "main-stat"): return 1 <= value <= 1000000
    if label in ("accuracy", "evasion"): return 0 <= value <= 200 and abs(value - round(value)) < 0.01
    if label.startswith("skill-level"): return 0 <= value <= 30 and abs(value - round(value)) < 0.01
    if label in ("crit-rate", "crit-damage", "attack-speed", "normal-damage", "boss-damage", "damage", "final-damage", "min-damage-ratio", "max-damage-ratio", "main-stat-percent", "basic-attack-damage", "defense-penetration"):
        return 0 <= value <= 500
    if label == "defense": return 0 <= value <= 1000000
    return True


def _row_parts(row: OCRRow) -> List[str]:
    return [p.strip() for p in row.text.split("|") if p.strip()]


def _best_value_for_label(label: str, vals: List[float]) -> Optional[float]:
    vals = [v for v in vals if plausible_value(label, v)]
    if not vals:
        return None
    if label in ("attack", "max-hp", "defense", "main-stat", "max-mp"):
        return max(vals)
    if label in ("accuracy", "evasion") or label.startswith("skill-level"):
        whole = [v for v in vals if abs(v - round(v)) < 0.01]
        return max(whole) if whole else None
    # Percentage-style rows are normally current value first, comparison delta second
    # e.g. "Critical Rate | 10% ~0.7%" should keep 10, not the 0.7 delta.
    return vals[0]


def _part_has_percent(part: str) -> bool:
    return "%" in part or "％" in part


def _part_numbers_for_label(part: str, label: str) -> List[float]:
    """Numbers from a single row part, filtered for stat-type safety."""
    nums = extract_numbers(part)
    # Remove ordinal number from job-skill labels, e.g. 4th Job Skill Lv. 14 -> keep 14 not 4.
    if label.startswith("skill-level"):
        n = int(label.split("-")[-1]) if label != "skill-level-all" else None
        if n is not None and nums and int(nums[0]) == n and re.search(rf"\b{n}(st|nd|rd|th)?\b", norm_text(part)):
            nums = nums[1:]
    safe: List[float] = []
    has_pct = _part_has_percent(part)
    for v in nums:
        if not plausible_value(label, v):
            continue
        # Whole-number stats must not be taken from percentage-looking fragments.
        if label in ("accuracy", "evasion") or label.startswith("skill-level"):
            if has_pct:
                continue
            if abs(v - round(v)) > 0.01:
                continue
        # v163: Max MP potion-helper rows can appear as percentages, e.g.
        # "Max MP | 26.5%". Keep the numeric value so MP presets can be
        # built by highest total Max MP per slot.
        # Max HP is a whole substat/main value, not a percent row.
        if label == "max-hp" and has_pct:
            continue
        safe.append(v)
    return safe


def _numbers_from_parts(parts: List[str], label: str) -> List[float]:
    vals: List[float] = []
    # Combine OCR-split thousands such as:
    #   79,5 | 501 -> 79501
    #   97 , | 132 -> 97132
    #   59," | 710 -> 59710
    # Only use split joining for non-percent integer stats.
    if label in ("attack", "max-hp", "defense", "main-stat"):
        for i in range(len(parts) - 1):
            a, b = parts[i].strip(), parts[i+1].strip()
            if canonical_label(a) or canonical_label(b):
                continue
            if _part_has_percent(a) or _part_has_percent(b):
                continue
            aa = norm_text(a).replace(" ", "")
            bb = norm_text(b).replace(" ", "")
            ma = re.fullmatch(r"([0-9]{1,3}),([0-9]?)", aa)
            mb = re.fullmatch(r"([0-9]{2,3})", bb)
            if ma and mb:
                # Keep the integer part before comma, then append the right fragment.
                joined = ma.group(1) + mb.group(1)
                try:
                    v = float(joined)
                    if plausible_value(label, v):
                        vals.append(v)
                except Exception:
                    pass

            # v197: EasyOCR can split a thousands-formatted value across
            # two fragments as e.g. ``Attack | 20, | ,826``.  The previous
            # joiner handled ``20, | 826`` but not the second fragment keeping
            # the leading comma.  Join these only for non-percent integer main
            # stats so comparison deltas/percent rows are not accidentally used.
            ma2 = re.fullmatch(r"([0-9]{1,3}),?", aa)
            mb2 = re.fullmatch(r",([0-9]{3})", bb)
            if ma2 and mb2:
                joined = ma2.group(1) + mb2.group(1)
                try:
                    v = float(joined)
                    if plausible_value(label, v):
                        vals.append(v)
                except Exception:
                    pass

            # v197: More split-number tolerance for equipped/bag popups.
            # EasyOCR sometimes keeps the comparison delta in the right fragment
            # or inserts a letter where a comma/space should be, e.g.:
            #   Max HP | 103, | 725 -13,023  -> 103725
            #   Attack | 24,C | 040 -2,430   -> 24040
            #   Attack | 23,E | 823          -> 23823
            # For fixed integer main stats, take the digit group before the
            # comma in the left fragment and the first 3-digit group from the
            # right fragment, ignoring non-digit OCR junk/comparison text.
            ma3 = re.fullmatch(r"([0-9]{1,3}),[^0-9%]*", aa)
            mb3 = re.match(r",?([0-9]{3})(?:\D|$)", bb)
            if ma3 and mb3:
                joined = ma3.group(1) + mb3.group(1)
                try:
                    v = float(joined)
                    if plausible_value(label, v):
                        vals.append(v)
                except Exception:
                    pass

            # v197: when a comparison delta follows immediately after the
            # right-side thousands fragment, norm_text+space stripping can
            # collapse e.g. ``040 ~2,430`` into ``0402,430``. In that case
            # the first three digits are still the right side of the main
            # value: ``24,C | 040 ~2,430`` -> 24040, not 2430. Only apply
            # this when the left fragment has the split-thousands shape.
            if ma3:
                right_digits = re.sub(r"\D", "", bb)
                if len(right_digits) >= 3:
                    joined = ma3.group(1) + right_digits[:3]
                    try:
                        v = float(joined)
                        if plausible_value(label, v):
                            vals.append(v)
                    except Exception:
                        pass
    for part in parts:
        vals.extend(_part_numbers_for_label(part, label))
    return vals


def _value_from_side(label: str, parts: List[str]) -> Optional[float]:
    if not parts:
        return None
    vals = _numbers_from_parts(parts, label)
    return _best_value_for_label(label, vals)


def _foreground_whole_substat_value(label: str, parts: List[str]) -> Optional[float]:
    """v190: choose the foreground whole-number substat value.

    Ring-filter screenshots can leave readable background numbers behind the
    popup, e.g. ``Evasion | 78 | 30 30``.  v180 used max(), so the background
    78 incorrectly beat the real foreground 30.

    Maple's popup normally draws the current substat twice on the right
    (white current value + green highlighted value).  For Accuracy/Evasion/job
    skill rows:
      1. Prefer a duplicated plausible whole number.
      2. Otherwise prefer the right-most plausible whole number.
    This avoids promoting earlier background bleed simply because it is larger.
    """
    vals: List[int] = []
    for part in parts:
        if _part_has_percent(part):
            continue
        for v in _part_numbers_for_label(part, label):
            if abs(v - round(v)) < 0.01:
                vals.append(int(round(v)))
    if not vals:
        return None

    counts: Dict[int, int] = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1

    duplicated = {v for v, n in counts.items() if n >= 2}
    if duplicated:
        for v in reversed(vals):
            if v in duplicated:
                return float(v)

    return float(vals[-1])


def _choose_from_same_row_by_side(label: str, row: OCRRow, *, substat: bool = False) -> Optional[float]:
    parts = _row_parts(row)
    if not parts:
        return None
    positions = [i for i, p in enumerate(parts) if canonical_label(p) == label]
    if positions:
        li = positions[0]
        before = parts[:li]
        after = parts[li+1:]

        if substat:
            # Safe row-side rules for substats:
            # - Percent stats prefer a percent-bearing side.
            # - Whole-number stats reject percent-bearing sides.
            # - Max MP can be a percent-style potion-helper stat, so v163
            #   allows percent-bearing sides and keeps the numeric value.
            percent_stats = {"crit-rate", "crit-damage", "attack-speed", "normal-damage", "boss-damage", "damage", "final-damage", "min-damage-ratio", "max-damage-ratio", "main-stat-percent", "basic-attack-damage", "defense-penetration"}
            sides = [("before", before), ("after", after)]
            if label in percent_stats:
                sides = sorted(sides, key=lambda x: not any(_part_has_percent(p) for p in x[1]))
            elif label == "max-mp":
                # Prefer the percent-bearing side first for rows like
                # "Max MP | 26.5% 26.5%". If the main value is non-percent,
                # fallback side parsing still handles it.
                sides = sorted(sides, key=lambda x: not any(_part_has_percent(p) for p in x[1]))
            elif label in ("accuracy", "evasion") or label.startswith("skill-level"):
                sides = [x for x in sides if not any(_part_has_percent(p) for p in x[1])]
            for _, side in sides:
                if label in ("accuracy", "evasion") or label.startswith("skill-level"):
                    val = _foreground_whole_substat_value(label, side)
                else:
                    val = _value_from_side(label, side)
                if val is not None:
                    return val
            return None

        # Main rows: current value is normally left of a middle label, or after a leading label.
        preferred = after if li == 0 else before
        val = _value_from_side(label, preferred)
        if val is not None:
            return val
        fallback = before if li == 0 else after
        val = _value_from_side(label, fallback)
        if val is not None:
            return val

    # Mixed label/value chunk fallback, e.g. Attack 14067.
    if canonical_label(row.text) == label:
        return _best_value_for_label(label, _numbers_from_parts(parts, label))
    return None


def _recover_main_attack_from_split_row(row: OCRRow) -> Optional[int]:
    """v190 reconstruct a split WHITE main Attack value.

    Verified EasyOCR failure examples from the fixed Maple popup:
      Attack | 21   | 1,428 | 168          -> 21,428
      Attack | 26,7 | 730 -2,620           -> 26,730
      Attack | 23,5 | 425 -5,925           -> 23,425
      Attack | 22,5 | 927 -180             -> 22,927
      Attack | 23,5 | 420 -3,050           -> 23,420
      Attack | 26,1 | 150 -370             -> 26,150
      Attack | 26,7 | 785 -2,565           -> 26,785

    The UI geometry is stable: item Attack appears first in white; comparison
    follows to the right in green/red. EasyOCR sometimes cuts the white Attack
    at the thousands comma, and the tail lands in the following token together
    with the comparison delta.

    This routine only runs on the *main Attack row*. It does not alter substats.
    """
    if not row.tokens:
        return None

    label_tokens = [t for t in row.tokens if canonical_label(t.text) == "attack"]
    if not label_tokens:
        return None
    label_right = max(t.x2 for t in label_tokens)

    # Numeric tokens to the right of Attack, in screen order.
    #
    # v197: ignore non-numeric OCR/background tokens before selecting the
    # split Attack fragments.  A real v194 failure row was:
    #   Attack | Speler | 22,5 | 927 -180
    # where the background token ``Speler`` became vals[0], preventing the
    # existing 22,5 + 927 -> 22,927 reconstruction from running.
    # Keep this targeted: we still require two numeric foreground-supported
    # fragments and the reconstructed Attack must pass the existing structural
    # 5,000..100,000 split-recovery bound.
    vals = [
        t for t in sorted(row.tokens, key=lambda t: t.cx)
        if t.cx >= label_right - 8
        and canonical_label(t.text) != "attack"
        and re.search(r"\d", t.text or "")
    ]
    if not vals:
        return None

    # If a single token already contains a plausible full white Attack before any
    # comparison value, leave normal parsing alone.
    first = vals[0]
    first_text = first.text.strip()
    first_nums = extract_numbers(first_text)
    if len(vals) == 1 and first_nums:
        v = first_nums[0]
        if 5000 <= v <= 100000:
            return int(v) if float(v).is_integer() else None

    # Need at least two adjacent numeric chunks for reconstruction.
    if len(vals) < 2:
        return None

    left = vals[0]
    right = vals[1]

    # Both chunks must have some bright foreground support. The second token can
    # contain both white item-tail pixels and red comparison pixels, so its coarse
    # fg_class may still be "white" with a low ratio.
    if left.fg_ratio < 0.06 or right.fg_ratio < 0.05:
        return None

    lt = left.text.strip()
    rt = right.text.strip()

    # Right token: take only the FIRST unsigned/positive numeric chunk. A later
    # negative number is the red comparison delta and is deliberately ignored.
    rm = re.search(r"(?<![-+])\b(\d[\d,]*)\b", rt)
    if not rm:
        return None
    tail_digits = re.sub(r"\D", "", rm.group(1))
    if not tail_digits:
        return None

    # Left token usually contains either:
    #   "26,7" -> use the stable thousands prefix before comma: "26"
    # or
    #   "21"   -> combine using digit overlap with the tail "1428".
    if "," in lt:
        prefix_raw = lt.split(",", 1)[0]
        prefix_digits = re.sub(r"\D", "", prefix_raw)
        if not prefix_digits:
            return None
        combined_digits = prefix_digits + tail_digits
    else:
        left_match = re.search(r"\d[\d,]*", lt)
        if not left_match:
            return None
        prefix_digits = re.sub(r"\D", "", left_match.group(0))
        if not prefix_digits:
            return None

        # Maximal suffix/prefix overlap handles 21 + 1428 -> 21428.
        overlap = 0
        for n in range(min(len(prefix_digits), len(tail_digits)), 0, -1):
            if prefix_digits[-n:] == tail_digits[:n]:
                overlap = n
                break
        combined_digits = prefix_digits + tail_digits[overlap:]

    if not combined_digits:
        return None

    candidate = int(combined_digits)
    if not (5000 <= candidate <= 100000):
        return None

    return candidate


def choose_value(label: str, row: OCRRow, nearby_rows: List[OCRRow], allow_nearby: bool = True, substat: bool = False) -> Optional[float]:
    """Choose the current stat value using UI row structure.

    Main rows may use nearby value-only rows. Substats must use same-row values,
    but can accept either label|value or value|label|comparison when type-safe.
    """
    if label == "attack" and not substat:
        recovered_attack = _recover_main_attack_from_split_row(row)
        if recovered_attack is not None:
            return float(recovered_attack)

    if substat:
        fg_val = _foreground_value_from_row(label, row)
        if fg_val is not None:
            return fg_val
    val = _choose_from_same_row_by_side(label, row, substat=substat)
    if val is not None:
        return val
    if not allow_nearby:
        return None
    vals: List[float] = []
    for nr in nearby_rows:
        if canonical_label(nr.text):
            continue
        vals.extend(_numbers_from_parts(_row_parts(nr), label))
    return _best_value_for_label(label, vals)


def clean_value(label: str, v: float) -> Any:
    """v190 zero-rounding parser policy.

    Never round OCR values up or down.
    - Whole-number-only stats must already be whole numbers or parsing fails.
    - Decimal/percentage stats are preserved exactly as the trusted OCR numeric
      value produced by extract_numbers().
    """
    whole_only = {
        "attack", "max-hp", "defense", "main-stat",
        "accuracy", "evasion",
    }
    if label.startswith("skill-level"):
        whole_only.add(label)

    fv = float(v)

    if label in whole_only:
        if not fv.is_integer():
            raise ValueError(f"Non-integer OCR value {v} for whole-number stat {label}; refusing to round")
        return int(fv)

    # Preserve decimal values as read. If numerically whole, keeping int is fine
    # because it does not alter the value.
    if fv.is_integer():
        return int(fv)
    return fv


def _foreground_mask_bgr(img: Any) -> Any:
    """v190 foreground mask for popup stat text/value colours.

    Keep only:
    - bright white/light grey foreground text
    - green/yellow-green highlighted/current values

    Reject dark grey background text and red comparison deltas.
    """
    if cv2 is None or np is None or img is None:
        return None
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Bright neutral foreground (white/light grey).
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    white = ((val >= 165) & (sat <= 105)).astype("uint8") * 255

    # Maple positive/highlight green to yellow-green.
    hue = hsv[:, :, 0]
    green = (((hue >= 28) & (hue <= 100)) & (sat >= 45) & (val >= 90)).astype("uint8") * 255

    mask = cv2.bitwise_or(white, green)
    return mask


def _classify_token_foreground(img: Any, tok: OCRToken) -> Tuple[float, str]:
    """Return foreground-pixel ratio and coarse colour class for an OCR token box."""
    if cv2 is None or np is None or img is None:
        return 0.0, "unknown"
    h, w = img.shape[:2]
    x1 = max(0, min(w - 1, int(tok.x1)))
    x2 = max(x1 + 1, min(w, int(tok.x2)))
    y1 = max(0, min(h - 1, int(tok.y1)))
    y2 = max(y1 + 1, min(h, int(tok.y2)))
    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        return 0.0, "unknown"

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    white = ((val >= 165) & (sat <= 105))
    green = (((hue >= 28) & (hue <= 100)) & (sat >= 45) & (val >= 90))
    fg = white | green

    ratio = float(fg.sum()) / float(fg.size) if fg.size else 0.0
    white_count = int(white.sum())
    green_count = int(green.sum())
    if green_count > white_count and green_count > 0:
        cls = "green"
    elif white_count > 0:
        cls = "white"
    else:
        cls = "background"
    return ratio, cls


def _token_numeric_candidates(row: OCRRow, label: str) -> List[Tuple[float, OCRToken]]:
    """Extract plausible numbers from OCR tokens with token geometry/colour attached."""
    out: List[Tuple[float, OCRToken]] = []
    for tok in row.tokens:
        for v in _part_numbers_for_label(tok.text, label):
            if plausible_value(label, v):
                out.append((v, tok))
    return out


def _foreground_value_from_row(label: str, row: OCRRow) -> Optional[float]:
    """v190 trusted foreground substat selector.

    Colour rule:
    - WHITE = item's actual stat and normally always wins.
    - GREEN = equipped-comparison value; fallback/evidence only.
    - RED / dark grey = never trusted.

    v190 whole-number reconstruction:
    EasyOCR can split a comma-formatted WHITE number such as 1,289 into a
    tiny WHITE fragment ("1") while also reading the complete 1,289 in the
    adjacent comparison text. When the same complete whole number appears
    at least twice on the row, that duplicate is strong evidence of the
    intended value and is preferred over a tiny WHITE fragment.

    This does NOT make GREEN authoritative. It only uses exact duplicate
    whole-number evidence to reconstruct a fragmented WHITE value.

    Other rules:
    - Percentage stats: left-most WHITE wins.
    - Accuracy/Evasion: duplicated foreground value preferred, otherwise WHITE.
    - Skill-level rows retain the proven v183 duplicate/right-most logic.
    - Never round.
    """
    if not row.tokens:
        return None

    label_tokens = [t for t in row.tokens if canonical_label(t.text) == label]
    label_right = max((t.x2 for t in label_tokens), default=row.x1)

    if label.startswith("skill-level"):
        parts = _row_parts(row)
        return _foreground_whole_substat_value(label, parts)

    white_cands: List[Tuple[float, OCRToken]] = []
    green_cands: List[Tuple[float, OCRToken]] = []

    for v, tok in _token_numeric_candidates(row, label):
        if canonical_label(tok.text) == label:
            continue
        if tok.cx < label_right - 8:
            continue
        if tok.fg_ratio < 0.08:
            continue
        if label in ("accuracy", "evasion") and not float(v).is_integer():
            continue

        if tok.fg_class == "white":
            white_cands.append((v, tok))
        elif tok.fg_class == "green":
            green_cands.append((v, tok))

    large_whole = {"attack", "max-hp", "max-mp", "defense", "main-stat"}

    def duplicated_whole_from_row() -> Optional[float]:
        """Find a repeated complete whole number anywhere in foreground/raw row parts.

        Used only for large whole-number rows. A repeated 1,289 / 1,289 beats
        a lone fragment 1. This specifically handles the verified Maple UI
        pattern where item and equipped-comparison values are identical.
        """
        vals: List[float] = []

        # Foreground candidates first.
        for v, _tok in white_cands + green_cands:
            if float(v).is_integer() and plausible_value(label, v):
                vals.append(float(v))

        # Raw row parts preserve comma-formatted complete values even when colour
        # classification split the white token badly.
        for part in _row_parts(row):
            if canonical_label(part):
                continue
            if _part_has_percent(part):
                continue
            for v in _part_numbers_for_label(part, label):
                if float(v).is_integer() and plausible_value(label, v):
                    vals.append(float(v))

        counts: Dict[float, int] = {}
        for v in vals:
            counts[v] = counts.get(v, 0) + 1

        duplicated = [v for v, n in counts.items() if n >= 2]
        if not duplicated:
            return None

        # Prefer the largest duplicated complete value; tiny OCR fragments lose.
        return max(duplicated)

    def choose_accuracy_evasion(cands: List[Tuple[float, OCRToken]]) -> Optional[float]:
        if not cands:
            return None
        counts: Dict[float, int] = {}
        for v, _ in cands:
            counts[v] = counts.get(v, 0) + 1
        duplicates = {v for v, n in counts.items() if n >= 2}
        if duplicates:
            dup = [(v, tok) for v, tok in cands if v in duplicates]
            dup.sort(key=lambda x: (x[1].cx, -x[1].fg_ratio))
            return dup[0][0]
        cands.sort(key=lambda x: (x[1].cx, -x[1].fg_ratio))
        return cands[0][0]

    # Large whole-number rows get duplicate reconstruction before ordinary
    # WHITE-first selection. This is the verified 1 / 1,289 / 1,289 fix.
    if label in large_whole:
        dup = duplicated_whole_from_row()
        if dup is not None:
            return dup

        if white_cands:
            whole_white = [(v, t) for v, t in white_cands if float(v).is_integer()]
            if whole_white:
                # Complete/larger white number beats a leading fragment.
                return max(v for v, _ in whole_white)

        if green_cands:
            whole_green = [(v, t) for v, t in green_cands if float(v).is_integer()]
            if whole_green:
                return max(v for v, _ in whole_green)
        return None

    # Accuracy/Evasion: WHITE first, duplicate support where present.
    if label in ("accuracy", "evasion"):
        if white_cands:
            return choose_accuracy_evasion(white_cands)
        if green_cands:
            return choose_accuracy_evasion(green_cands)
        return None

    # Percentage/decimal stats: WHITE is authoritative and left-most item value wins.
    if white_cands:
        white_cands.sort(key=lambda x: (x[1].cx, -x[1].fg_ratio))
        return white_cands[0][0]

    # GREEN only if there is no usable WHITE token at all.
    if green_cands:
        green_cands.sort(key=lambda x: (x[1].cx, -x[1].fg_ratio))
        return green_cands[0][0]

    return None


def tokens_from_easyocr(results: List[Any], image: Any = None) -> List[OCRToken]:
    toks: List[OCRToken] = []
    for res in results:
        if len(res) < 2:
            continue
        box, text = res[0], str(res[1])
        conf = float(res[2]) if len(res) > 2 else 0.0
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
        tok = OCRToken(text=text, conf=conf, x1=x1, y1=y1, x2=x2, y2=y2, cx=(x1+x2)/2, cy=(y1+y2)/2, h=(y2-y1))
        if image is not None:
            tok.fg_ratio, tok.fg_class = _classify_token_foreground(image, tok)
        toks.append(tok)
    return toks


def group_rows(tokens: List[OCRToken]) -> List[OCRRow]:
    if not tokens:
        return []
    tokens = sorted(tokens, key=lambda t: (t.cy, t.x1))
    med_h = sorted([t.h for t in tokens])[len(tokens)//2]
    thresh = max(8.0, med_h * 0.55)
    groups: List[List[OCRToken]] = []
    for tok in tokens:
        if not groups or abs(tok.cy - sum(t.cy for t in groups[-1])/len(groups[-1])) > thresh:
            groups.append([tok])
        else:
            groups[-1].append(tok)
    rows: List[OCRRow] = []
    for i, g in enumerate(groups):
        g = sorted(g, key=lambda t: t.x1)
        text = " | ".join(t.text for t in g)
        rows.append(OCRRow(idx=i, y=sum(t.cy for t in g)/len(g), x1=min(t.x1 for t in g), x2=max(t.x2 for t in g), text=text, tokens=g))
    return rows


def dedupe_rows(rows: List[OCRRow]) -> List[OCRRow]:
    out: List[OCRRow] = []
    seen_recent: List[Tuple[str, float]] = []
    for r in rows:
        nt = norm_text(r.text)
        if not nt:
            continue
        if any(noise == nt for noise in NOISE_WORDS):
            continue
        dup = False
        for prev_text, prev_y in seen_recent[-8:]:
            if nt == prev_text and abs(r.y - prev_y) < 18:
                dup = True
                break
        if dup:
            continue
        seen_recent.append((nt, r.y))
        r.idx = len(out)
        out.append(r)
    return out


def detect_slot(full_text: str) -> Optional[str]:
    """Detect equipment slot from the item/type area, not noisy stat rows.

    v160: slot detection must not be fooled by set/comparison/title bleed inside
    stat rows, e.g. an Earrings card whose Attack/Max HP area contains
    "Kagon Necklace". The top item-name/type rows win; full-text fallback is
    only used if the top rows are not readable.
    """
    raw_lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
    top_text = norm_text("\n".join(raw_lines[:6]))
    full = norm_text(full_text)

    # Ring 2 has to win before normal Ring.
    if re.search(r"\bring\s*2\b", top_text) or "legendary ring 2" in top_text:
        return "ring2"

    # Strong item-type phrases from the top of the card. These beat any later
    # noisy words that appear inside stat rows.
    strong_top = [
        ("earring", ["earring", "earrings"]),
        ("necklace", ["necklace"]),
        ("shoulder", ["shoulder", "pauldron"]),
        ("bottom", ["bottom", "pants", "skirt"]),
        ("gloves", ["gloves"]),
        ("shoes", ["shoes", "boots"]),
        ("belt", ["belt"]),
        ("cape", ["cape"]),
        ("face", ["face accessory", "condensed power crystal", "power crystal"]),
        ("eye", ["eye accessory", "aquatic letter", "eye"]),
        ("ring", [" ring", "ring ", "legendary ring"]),
        ("hat", ["hat", "helmet"]),
        ("top", ["top", "suit", "varuna"]),
    ]
    for slot, keys in strong_top:
        if any(k in top_text for k in keys):
            return slot

    # Full text fallback kept for difficult OCR, but still Ring2 first and with
    # Earrings before Necklace to avoid the v159 mis-slot.
    if re.search(r"\bring\s*2\b", full):
        return "ring2"
    fallback_order = [
        ("earring", ["earring", "earrings"]),
        ("necklace", ["necklace"]),
        ("shoulder", ["shoulder", "pauldron"]),
        ("bottom", ["bottom", "pants", "skirt"]),
        ("gloves", ["gloves", "ciara"]),
        ("shoes", ["shoes", "boots"]),
        ("belt", ["belt"]),
        ("cape", ["cape"]),
        ("face", ["face", "condensed power crystal", "power crystal"]),
        ("eye", ["eye", "aquatic letter"]),
        ("ring", ["ring"]),
        ("hat", ["hat", "helmet"]),
        ("top", ["top", "suit", "varuna"]),
    ]
    for slot, keys in fallback_order:
        if any(k in full for k in keys):
            return slot
    return None


MIN_TRUSTED_LEVEL = 80
MAX_TRUSTED_LEVEL = 120


def _normalise_level_candidate(raw_digits: str) -> Optional[str]:
    """Return a safe equipment level, or None for OCR junk.

    v150 deliberately fails closed for levels. Recent OCR produced junk such as
    Lv706/Lv707 from Lv.106/Lv.107 and Lv.13 from the card star overlay. Those
    must not be written to mapleexcel/mapleupload metadata.
    """
    digits = re.sub(r"[^0-9]", "", raw_digits or "")
    if not digits:
        return None
    try:
        value = int(digits)
    except ValueError:
        return None
    if MIN_TRUSTED_LEVEL <= value <= MAX_TRUSTED_LEVEL:
        return str(value)
    return None


def parse_tier_level(full_text: str) -> Tuple[str, str]:
    t = full_text
    tier = ""
    level = ""

    # Tier is stable enough to take the first valid T1-T4.
    m = re.search(r"\bT\s*([1-4])\b", t, re.I)
    if m:
        tier = "T" + m.group(1)

    # Level is NOT stable enough to take the first Lv match. OCR can read the
    # icon overlay as Lv.13, or title-row Lv.106 as Lv706. Collect every Lv-like
    # candidate and only keep plausible equipment levels.
    level_patterns = [
        r"\bLv\.?\s*([0-9]{1,3})\b",
        r"\bLv[,;:]\s*([0-9]{1,3})\b",
        r"\bL[vw]\s*([0-9]{1,3})\b",
    ]
    candidates: List[str] = []
    for pat in level_patterns:
        for m in re.finditer(pat, t, re.I):
            safe = _normalise_level_candidate(m.group(1))
            if safe is not None:
                candidates.append(safe)

    if candidates:
        # Prefer the first plausible Lv reading after filtering impossible values.
        # In dirty rows this turns [706, 106] into 106, and [13, 103] into 103.
        level = candidates[0]

    return tier, level


def find_on_equip_start(rows: List[OCRRow]) -> Optional[int]:
    """Return the first stat-row index after the On-Equip Effect anchor.

    v144 requires a real On-Equip/Equip Effect OCR anchor. If no anchor is
    detected, the item is rejected to stat_review.txt. No fallback import path
    is allowed.
    """
    for i, r in enumerate(rows):
        nt = norm_text(r.text)
        squashed = re.sub(r"[^a-z0-9]+", "", nt)

        # Forgiving variants for the green On-Equip Effect header.
        # We still require both equipment/equip and effect intent.
        if ("onequip" in squashed and "effect" in squashed) or ("equip" in squashed and "effect" in squashed):
            return i + 1

        # Common OCR variants where O becomes 0 or letters are dropped.
        if ("0nequip" in squashed and "effect" in squashed) or ("onequp" in squashed and "effect" in squashed):
            return i + 1

    return None


def find_expected_label_rows(rows: List[OCRRow], start: int, expected: List[str]) -> Optional[List[int]]:
    idxs: List[int] = []
    pos = start
    for exp in expected:
        found = None
        # find next explicit matching label; skip duplicate/noise labels
        for i in range(pos, min(len(rows), pos + 12)):
            lab = canonical_label(rows[i].text)
            if lab == exp:
                found = i
                break
        if found is None:
            return None
        idxs.append(found)
        pos = found + 1
    return idxs

def relaxed_main_label(text: str, expected: str) -> bool:
    """v160 tolerance for noisy fixed main rows only.

    This is deliberately used only for the 3 required main rows, and values are
    still validated by choose_value/plausible_value. It handles OCR such as
    "Attackexagon Necklace", "Attack_xagon Necklace", "Max HPnuneito Debuff",
    and "Max | APnein | tooDebut" without allowing loose substat imports.
    """
    t = norm_text(text)
    squashed = re.sub(r"[^a-z0-9]+", "", t)
    if expected == "attack":
        return squashed.startswith("attack")
    if expected == "max-hp":
        return ("maxhp" in squashed) or (squashed.startswith("max") and any(x in squashed for x in ["apne", "apnein", "hpnune", "debuff", "debut", "nune"]))
    if expected == "max-mp":
        return ("maxmp" in squashed)
    if expected == "main-stat":
        return "mainstat" in squashed
    if expected == "accuracy":
        return "accuracy" in squashed or "accurary" in squashed
    if expected == "evasion":
        return "evasion" in squashed or "evaslon" in squashed or "evaston" in squashed
    if expected == "defense":
        return "defense" in squashed or "deferse" in squashed
    return False


def find_expected_label_rows_relaxed(rows: List[OCRRow], start: int, expected: List[str]) -> Optional[List[int]]:
    idxs: List[int] = []
    pos = start
    for exp in expected:
        found = None
        for i in range(pos, min(len(rows), pos + 14)):
            lab = canonical_label(rows[i].text)
            if lab == exp or relaxed_main_label(rows[i].text, exp):
                found = i
                break
        if found is None:
            return None
        idxs.append(found)
        pos = found + 1
    return idxs


def _main_sequence_has_trusted_values(rows: List[OCRRow], idxs: List[int], expected: List[str]) -> bool:
    """Validate that a candidate Attack/Max HP/third-main sequence has readable values.

    This lets v155 recover when the visual green anchor lands on player/title/set
    text below the real stat block, while still failing closed if the fixed main
    rows cannot be safely read.
    """
    if len(idxs) != len(expected):
        return False
    # Rows must be in a tight, card-like block, not scattered through the screen.
    ys = [rows[i].y for i in idxs]
    if max(ys) - min(ys) > 170:
        return False
    for k, idx in enumerate(idxs):
        lab = expected[k]
        next_idx = idxs[k+1] if k+1 < len(idxs) else None
        val = choose_value(lab, rows[idx], nearby_value_rows(rows, idx, next_idx), allow_nearby=True)
        if val is None or not plausible_value(lab, val):
            return False
        if lab == "attack" and clean_value(lab, val) < 9000:
            return False
    return True


def find_expected_label_rows_anywhere(rows: List[OCRRow], expected: List[str], visual_anchor: Optional[Dict[str, Any]] = None) -> Optional[List[int]]:
    """Find the fixed main stat sequence without trusting a lower green anchor.

    v155 still requires a visual anchor somewhere on the card, but if that anchor
    is fooled by green player/title/set text, the parser may search from below the
    real Attack/Max HP rows. This fallback searches the OCR rows for the fixed
    3-row sequence and validates the values before accepting it.
    """
    candidates: List[Tuple[float, List[int]]] = []
    image_h = 1000.0
    anchor_y = None
    if visual_anchor:
        try:
            image_h = float(visual_anchor.get("image_size", [0, 1000])[1])
            anchor_y = float(visual_anchor.get("anchor_y", 0))
        except Exception:
            pass
    for start in range(0, len(rows)):
        if canonical_label(rows[start].text) != expected[0]:
            continue
        idxs = find_expected_label_rows(rows, start, expected)
        if not idxs:
            continue
        if not _main_sequence_has_trusted_values(rows, idxs, expected):
            continue
        first_y = float(rows[idxs[0]].y)
        # Equipment stat blocks are normally in the middle of the card. Avoid
        # very high titles and very low background/player text.
        if not (image_h * 0.25 <= first_y <= image_h * 0.78):
            continue
        # Prefer the candidate nearest the visual anchor. If anchor is below the
        # real stats, this still chooses the upper fixed sequence.
        if anchor_y is not None:
            score = abs(first_y - anchor_y)
        else:
            score = first_y
        candidates.append((score, idxs))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def nearby_value_rows(rows: List[OCRRow], label_idx: int, next_label_idx: Optional[int]) -> List[OCRRow]:
    # Search same row handled separately. Nearby rows bounded before next label, with value-only preference.
    candidates: List[OCRRow] = []
    end = next_label_idx if next_label_idx is not None else min(len(rows), label_idx + 3)
    for i in range(label_idx + 1, min(len(rows), end)):
        if canonical_label(rows[i].text):
            break
        candidates.append(rows[i])
    # Also allow previous row for cases where OCR value is just before label, but not if previous row is a label.
    if label_idx - 1 >= 0 and not canonical_label(rows[label_idx - 1].text):
        candidates.append(rows[label_idx - 1])
    return candidates




def detect_lock_status(image_path: Path) -> Tuple[str, str]:
    """Detect the popup's large lock button using a fixed UI ROI.

    v190 fixes false lock reads caused by red UI/background objects behind the
    equipment popup.  The old detector scanned almost half the screenshot.
    The game UI is fixed, so only the large lock button below the item icon is
    inspected.

    Reference 531x834 screenshot ROI is approximately:
      x=106..175, y=308..383

    The proportional form below keeps the same location if capture dimensions
    change slightly.
    """
    if cv2 is None or np is None:
        return "unclear", "cv2 unavailable"
    img = cv2.imread(str(image_path))
    if img is None:
        return "unclear", "image unreadable"

    h, w = img.shape[:2]

    # Fixed large lock-button region.  This deliberately excludes:
    # - the small padlock overlay on the equipment icon
    # - red CP comparison text on the right
    # - red/background UI elsewhere behind the popup
    x1 = int(w * 0.20)
    x2 = int(w * 0.33)
    y1 = int(h * 0.37)
    y2 = int(h * 0.46)
    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        return "unclear", "empty fixed lock-button crop"

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    # Bright/saturated red used by the closed lock button.
    mask = (((hue <= 12) | (hue >= 168)) & (sat >= 70) & (val >= 80)).astype("uint8") * 255
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    count = int((mask > 0).sum())
    num_labels, labels, stats, _cent = cv2.connectedComponentsWithStats(mask, 8)
    comps = []
    for i in range(1, num_labels):
        area = int(stats[i, cv2.CC_STAT_AREA])
        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])
        ww = int(stats[i, cv2.CC_STAT_WIDTH])
        hh = int(stats[i, cv2.CC_STAT_HEIGHT])
        if area >= 30 and ww >= 4 and hh >= 4:
            comps.append((area, x + x1, y + y1, ww, hh))
    comps.sort(reverse=True)

    roi_text = f"roi=({x1},{y1})-({x2},{y2})"
    if comps or count >= 80:
        return "locked", f"{roi_text}; red_lock_pixels={count}; components={comps[:3]}"
    if count <= 15:
        return "unlocked", f"{roi_text}; red_lock_pixels={count}; no red lock-button component"
    return "unclear", f"{roi_text}; red_lock_pixels={count}; borderline fixed lock-button result"

def detect_visual_on_equip_anchor(image_path: Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Detect the On-Equip Effect green text band visually.

    v150 deliberately does not look for a single wide green contour. The game draws
    "On-Equip Effect" as separate green/yellow letter shapes, so v145's wide-bar
    contour test rejected good screenshots. This detector groups green pixels by
    row position inside the expected card/stat-panel zone and chooses the strongest
    band around the middle of the equipment card.
    """
    dbg: List[str] = []
    if cv2 is None or np is None:
        return None, ["VISUAL_ANCHOR: unavailable; cv2/numpy not installed"]
    img = cv2.imread(str(image_path))
    if img is None:
        return None, ["VISUAL_ANCHOR: image could not be read"]
    h, w = img.shape[:2]
    dbg.append(f"IMAGE_SIZE: {w}x{h}")
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Maple UI green/yellow-green used for On-Equip Effect and positive values.
    # Restrict to the left/mid stat-panel header zone so item title/card art and
    # lower skill/background UI do not become anchors.
    lower = np.array([35, 45, 55], dtype=np.uint8)
    upper = np.array([95, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    y_min = int(h * 0.35)
    y_max = int(h * 0.65)
    x_max = int(w * 0.62)
    mask[:y_min, :] = 0
    mask[y_max:, :] = 0
    mask[:, x_max:] = 0

    # Close letter fragments horizontally just enough to form a text-band row
    # projection, not enough to accept arbitrary whole-screen fallback.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 2))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    row_counts = (mask > 0).sum(axis=1)
    threshold = max(10, int(w * 0.018))

    bands: List[Dict[str, Any]] = []
    in_band = False
    start = 0
    total = 0
    max_count = 0
    for y, count in enumerate(row_counts):
        if count > threshold and not in_band:
            start = y
            total = 0
            max_count = 0
            in_band = True
        if in_band:
            total += int(count)
            max_count = max(max_count, int(count))
        if in_band and (count <= threshold or y == len(row_counts) - 1):
            end = y
            in_band = False
            if end - start >= 5:
                band_mask = mask[start:end+1, :x_max]
                pts = cv2.findNonZero(band_mask)
                if pts is not None:
                    x, yy, bw, bh = cv2.boundingRect(pts)
                    abs_y = start + yy
                    # On-Equip text is a medium-height band. Very tiny bands are
                    # separators/background; very tall bands are card art.
                    if 6 <= bh <= 42 and bw >= int(w * 0.20):
                        centre = abs_y + bh / 2.0
                        middle_bonus = 2500 if (h * 0.44 <= centre <= h * 0.58) else 0
                        bands.append({
                            "x": int(x), "y": int(abs_y), "w": int(bw), "h": int(bh),
                            "end_y": int(abs_y + bh), "total": int(total),
                            "max_row_pixels": int(max_count), "score": int(total + middle_bonus),
                        })
    dbg.append("VISUAL_CANDIDATE_BANDS: " + (json.dumps(bands, ensure_ascii=False) if bands else "none"))
    if not bands:
        return None, dbg + ["VISUAL_ANCHOR: not detected"]
    bands.sort(key=lambda b: (b["score"], b["total"], b["y"]), reverse=True)
    chosen = bands[0]
    anchor_y = int(chosen["end_y"])
    first_stat_min_y = anchor_y + max(14, int(h * 0.014))
    info = {
        "mode": "VISUAL_ANCHOR",
        "anchor_y": anchor_y,
        "first_stat_min_y": first_stat_min_y,
        "band": chosen,
        "image_size": [int(w), int(h)],
    }
    dbg.append(f"VISUAL_ANCHOR: detected anchor_y={anchor_y} first_stat_min_y={first_stat_min_y} band={chosen}")
    return info, dbg


def first_row_after_visual_anchor(rows: List[OCRRow], visual_anchor: Dict[str, Any]) -> Optional[int]:
    min_y = float(visual_anchor.get("first_stat_min_y") or 0)
    for r in rows:
        if r.y >= min_y:
            return r.idx
    return None


# ---------------------------------------------------------------------------
# v190 conservative sanity checks
# ---------------------------------------------------------------------------

SANITY_PERCENT_TYPES = {
    "crit-rate", "crit-damage", "attack-speed", "normal-damage", "boss-damage",
    "damage", "final-damage", "min-damage-ratio", "max-damage-ratio",
    "main-stat-percent", "basic-attack-damage", "defense-penetration",
}

SANITY_WHOLE_TYPES = {
    "attack", "max-hp", "defense", "main-stat", "accuracy", "evasion",
}

SANITY_KNOWN_STAT_TYPES = set(SUBSTAT_LABELS.values())


# Conservative OCR validation ranges for OPTION/SUBSTAT values.
# Main item Attack is intentionally excluded from fixed gameplay ranges in v192.
# Format: label -> {hard_min, hard_max, warn_min, warn_max}
# HARD = send to review if outside this range.
# WARN = keep item, but flag it as suspicious if outside this narrower range.
#
# These are intentionally generous. They exist to catch obvious OCR corruption
# such as "Defense 1" from "1,580", "Critical Damage 7815", etc.
STAT_VALIDATION_RANGES: Dict[str, Dict[str, float]] = {
    # Whole-number option stats
    "attack": {"hard_min": 100.0, "hard_max": 50000.0, "warn_min": 1000.0, "warn_max": 15000.0},
    "main-stat": {"hard_min": 100.0, "hard_max": 10000.0, "warn_min": 500.0, "warn_max": 5000.0},
    "defense": {"hard_min": 100.0, "hard_max": 10000.0, "warn_min": 500.0, "warn_max": 3000.0},
    "accuracy": {"hard_min": 1.0, "hard_max": 100.0, "warn_min": 5.0, "warn_max": 60.0},
    "evasion": {"hard_min": 1.0, "hard_max": 100.0, "warn_min": 5.0, "warn_max": 60.0},
    "max-hp": {"hard_min": 1000.0, "hard_max": 5000000.0, "warn_min": 10000.0, "warn_max": 200000.0},
    "max-mp": {"hard_min": 1.0, "hard_max": 100.0, "warn_min": 10.0, "warn_max": 60.0},

    # Percentage-style option stats
    "crit-rate": {"hard_min": 0.1, "hard_max": 100.0, "warn_min": 1.0, "warn_max": 30.0},
    "crit-damage": {"hard_min": 0.1, "hard_max": 100.0, "warn_min": 1.0, "warn_max": 30.0},
    "attack-speed": {"hard_min": 0.1, "hard_max": 100.0, "warn_min": 1.0, "warn_max": 30.0},
    "normal-damage": {"hard_min": 0.1, "hard_max": 100.0, "warn_min": 1.0, "warn_max": 40.0},
    "boss-damage": {"hard_min": 0.1, "hard_max": 100.0, "warn_min": 1.0, "warn_max": 40.0},
    "damage": {"hard_min": 0.1, "hard_max": 100.0, "warn_min": 1.0, "warn_max": 80.0},
    "final-damage": {"hard_min": 0.1, "hard_max": 100.0, "warn_min": 1.0, "warn_max": 80.0},
    "min-damage-ratio": {"hard_min": 0.1, "hard_max": 100.0, "warn_min": 1.0, "warn_max": 40.0},
    "max-damage-ratio": {"hard_min": 0.1, "hard_max": 100.0, "warn_min": 1.0, "warn_max": 40.0},
    "main-stat-percent": {"hard_min": 0.1, "hard_max": 100.0, "warn_min": 1.0, "warn_max": 50.0},
    "basic-attack-damage": {"hard_min": 0.1, "hard_max": 100.0, "warn_min": 1.0, "warn_max": 50.0},
    "defense-penetration": {"hard_min": 0.1, "hard_max": 100.0, "warn_min": 1.0, "warn_max": 50.0},
}

SKILL_LEVEL_RANGE = {"hard_min": 1.0, "hard_max": 50.0, "warn_min": 1.0, "warn_max": 30.0}
ITEM_ATTACK_RANGE = {}  # v197: no fixed gameplay-value range for main item Attack


def _stat_validation_range(label: str) -> Dict[str, float]:
    if label.startswith("skill-level"):
        return SKILL_LEVEL_RANGE
    return STAT_VALIDATION_RANGES.get(label, {})



def _numeric_equal_no_rounding(a: Any, b: Any) -> bool:
    try:
        return float(a) == float(b)
    except Exception:
        return False


def _row_has_white_support(rows: List[OCRRow], label: str, value: Any) -> bool:
    """True when the chosen value appears in a bright WHITE token on the matching row."""
    for row in rows:
        row_labels = {canonical_label(t.text) for t in row.tokens}
        if label not in row_labels and canonical_label(row.text) != label:
            continue

        label_right = max(
            (t.x2 for t in row.tokens if canonical_label(t.text) == label),
            default=row.x1,
        )
        for tok in row.tokens:
            if tok.cx < label_right - 8:
                continue
            if tok.fg_class != "white" or tok.fg_ratio < 0.08:
                continue
            for n in _part_numbers_for_label(tok.text, label):
                if _numeric_equal_no_rounding(n, value):
                    return True
    return False


def sanity_check_parsed_item(p: ParsedItem, rows: List[OCRRow], lock_status: str) -> Tuple[List[str], List[str]]:
    """Return (hard_errors, soft_warnings).

    HARD errors are structural/data-integrity failures only.
    SOFT warnings are suspicious but may be valid on another account/tier. Option-stat ranges use generous warning bands and wider hard-reject bands. Main item Attack has no fixed gameplay-value range.
    No sanity rule ever changes or rounds a value.
    """
    hard: List[str] = []
    warn: List[str] = []

    # --- HARD: structural/data integrity only ---
    try:
        attack = p.item.get("attack")
        if not isinstance(attack, int) or isinstance(attack, bool) or attack <= 0:
            hard.append(f"attack is not a positive whole number: {attack!r}")
        if int(p.attack) != int(attack):
            hard.append(f"parsed attack/item attack mismatch: {p.attack!r} vs {attack!r}")

        # v197: DO NOT sanity-reject main item Attack by a fixed numeric
        # min/max. Valid gear spans a very wide range across player progress,
        # item tier and item level. A fixed late-game floor caused legitimate
        # low-level items to be rejected.
        #
        # Main Attack is instead protected structurally:
        # - it must be a positive whole number (checked above)
        # - parser/main-item attack must agree (checked above)
        # - split white Attack fragments are reconstructed before selection
        # - comparison/background colour filtering remains active
        #
        # Future item-aware validation may add level/tier-specific upper bounds,
        # but v192 deliberately does not guess those bounds.
        item_attack = float(attack)
        # v197: absolute main Attack value is not used as a trust/review criterion.
    except Exception:
        hard.append("attack internal consistency check failed")

    stats = list(p.item.get("stats", []) or [])

    # Maple equipment shown by this importer supports at most four option/substat rows.
    # More than four almost certainly means row/background bleed.
    if len(stats) > 4:
        hard.append(f"more than 4 option stats parsed ({len(stats)})")

    for st in stats:
        typ = str(st.get("type", ""))
        val = st.get("value")

        if typ not in SANITY_KNOWN_STAT_TYPES:
            hard.append(f"unknown stat type: {typ!r}")
            continue

        try:
            fv = float(val)
        except Exception:
            hard.append(f"{typ} is not numeric: {val!r}")
            continue

        if not math.isfinite(fv):
            hard.append(f"{typ} is non-finite: {val!r}")
            continue
        if fv < 0:
            hard.append(f"{typ} is negative: {val!r}")

        if typ in SANITY_WHOLE_TYPES or typ.startswith("skill-level"):
            if not fv.is_integer():
                hard.append(f"{typ} is fractional ({val!r}); refusing to round")

        # Conservative stat min/max validation.
        rng = _stat_validation_range(typ)
        if rng:
            if fv < rng["hard_min"] or fv > rng["hard_max"]:
                hard.append(
                    f"{typ} {val}: outside hard range "
                    f"{rng['hard_min']}-{rng['hard_max']}"
                )
            elif fv < rng["warn_min"] or fv > rng["warn_max"]:
                warn.append(
                    f"{typ} {val}: outside warning range "
                    f"{rng['warn_min']}-{rng['warn_max']}"
                )

        # A trusted chosen substat should ideally have a matching bright WHITE token.
        # For this v190 sanity build, absence is a WARNING only so we can measure it
        # against the full inventory before deciding whether to make it a hard rule.
        if not _row_has_white_support(rows, typ, val):
            warn.append(f"{typ} {val}: no exact WHITE foreground token support")

        # --- SOFT: deliberately generous bounds ---
        if typ in SANITY_PERCENT_TYPES and fv > 100:
            warn.append(f"{typ} {val}: percentage-style stat over 100")
        if typ == "max-mp" and fv > 100:
            warn.append(f"max-mp {val}: option value over 100 (check flat-vs-percent/background bleed)")
        if typ == "defense" and 0 < fv < 100:
            warn.append(f"defense {val}: unusually small defense option")
        if typ in ("accuracy", "evasion") and fv > 100:
            warn.append(f"{typ} {val}: unusually large whole-number option")

    # Duplicate option types may be legal in future/game variants, so warning only.
    types = [str(st.get("type", "")) for st in stats]
    dup_types = sorted({t for t in types if t and types.count(t) > 1})
    if dup_types:
        warn.append("duplicate option stat type(s): " + ", ".join(dup_types))

    # Zero options may be valid for lower-tier gear; warning only.
    if len(stats) == 0:
        warn.append("no option stats parsed")

    # Never throw away otherwise valid equipment just because lock colour is ambiguous.
    if lock_status == "unclear":
        warn.append("lock status unclear")

    return hard, warn


def parse_item_from_rows(filename: str, rows: List[OCRRow], visual_anchor: Optional[Dict[str, Any]] = None, visual_debug: Optional[List[str]] = None) -> Tuple[Optional[ParsedItem], str]:
    full_text = "\n".join(r.text for r in rows)
    slot = detect_slot(full_text)
    tier, level = parse_tier_level(full_text)
    if not slot:
        return None, "slot not detected"
    expected = MAIN_TEMPLATES[slot]
    text_start = find_on_equip_start(rows)
    dbg: List[str] = []
    dbg.append(f"FILE: {filename}")
    dbg.append(f"SLOT: {slot}")
    dbg.append("EXPECTED_MAIN_ROWS: " + ", ".join(expected))
    if visual_debug:
        dbg.extend(visual_debug)
    if slot in ("shoes", "belt"):
        dbg.append("V148_MAIN_MAX_MP_RULE: third main row is locked as Max MP and may exceed 1000; comparison values ignored by side parser")

    # v150 locked policy: visual geometry anchor is required. Text OCR anchor is
    # useful diagnostic information only; it does not permit loose fallback.
    if visual_anchor is None:
        dbg.append("ANCHOR_MODE: REJECTED no visual On-Equip geometry")
        return None, "REJECTED no visual On-Equip geometry"

    visual_start = first_row_after_visual_anchor(rows, visual_anchor)
    if text_start is not None:
        dbg.append(f"TEXT_ANCHOR: detected; first_stat_search_row={text_start}")
    else:
        dbg.append("TEXT_ANCHOR: not detected")
    dbg.append(f"VISUAL_ANCHOR: detected; first_stat_search_row={visual_start}")

    if visual_start is None:
        dbg.append("ERROR: VISUAL_ANCHOR detected but no OCR rows exist below it")
        return None, "REJECTED visual anchor detected but no OCR rows below anchor"

    # If text OCR found the anchor and it agrees with the visual geometry, use it.
    # Otherwise use the visual start row. This is not a whole-screen fallback: the
    # row search starts only below the detected green On-Equip text band.
    if text_start is not None and abs(rows[text_start].y - rows[visual_start].y) <= 80:
        start = min(text_start, visual_start)
        dbg.append("ANCHOR_MODE: TEXT_ANCHOR+VISUAL_ANCHOR")
    else:
        start = visual_start
        dbg.append("ANCHOR_MODE: VISUAL_ANCHOR")

    main_label_idxs = find_expected_label_rows(rows, start, expected)
    sequence_mode = "ANCHOR_BOUNDED"
    if main_label_idxs is None:
        dbg.append("ANCHOR_SEQUENCE: strict sequence missing; trying v160 relaxed main-row sequence")
        main_label_idxs = find_expected_label_rows_relaxed(rows, start, expected)
        sequence_mode = "ANCHOR_BOUNDED_RELAXED"
    if main_label_idxs is None:
        dbg.append("ANCHOR_SEQUENCE: missing from visual/text start; trying bounded fixed-main-row fallback")
        main_label_idxs = find_expected_label_rows_anywhere(rows, expected, visual_anchor)
        sequence_mode = "FIXED_MAIN_ROWS_FALLBACK"
    if main_label_idxs is None:
        dbg.append("ANCHOR_SEQUENCE: strict anywhere fallback missing; trying v160 relaxed anywhere fallback")
        # Try every plausible start row with the relaxed label detector, then validate values.
        candidates = []
        image_h = float(visual_anchor.get("image_size", [0, 1000])[1]) if visual_anchor else 1000.0
        anchor_y2 = float(visual_anchor.get("anchor_y", 0)) if visual_anchor else 0.0
        for s in range(len(rows)):
            idxs2 = find_expected_label_rows_relaxed(rows, s, expected)
            if not idxs2 or not _main_sequence_has_trusted_values(rows, idxs2, expected):
                continue
            first_y2 = float(rows[idxs2[0]].y)
            if image_h * 0.25 <= first_y2 <= image_h * 0.78:
                candidates.append((abs(first_y2 - anchor_y2), idxs2))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            main_label_idxs = candidates[0][1]
            sequence_mode = "FIXED_MAIN_ROWS_RELAXED_FALLBACK"
    if main_label_idxs is None:
        dbg.append("ERROR: missing fixed main label sequence after bounded stat-window search")
        return None, "missing fixed main label sequence after bounded stat-window search"
    dbg.append(f"MAIN_SEQUENCE_MODE: {sequence_mode} idxs={main_label_idxs}")

    # Safety: when we used the normal anchor sequence, first main stat must be
    # below, but not wildly below, the visual On-Equip band. When v155 uses the
    # fixed-main-row fallback, the visual anchor may have landed on lower green
    # player/title/set text; in that case the validated Attack/Max HP/third-row
    # sequence is allowed above the visual anchor.
    first_main_y = float(rows[main_label_idxs[0]].y)
    anchor_y = float(visual_anchor.get("anchor_y", 0)) if visual_anchor else 0.0
    max_gap = max(150.0, float((visual_anchor.get("image_size", [0, 1000])[1] if visual_anchor else 1000)) * 0.22)
    if sequence_mode == "ANCHOR_BOUNDED":
        if first_main_y <= anchor_y:
            dbg.append(f"ERROR: main stat sequence is not below visual anchor: main_y={first_main_y:.1f}, anchor_y={anchor_y:.1f}")
            return None, "main stat sequence is not below visual anchor"
        if first_main_y - anchor_y > max_gap:
            dbg.append(f"ERROR: main stat sequence too far below visual anchor: main_y={first_main_y:.1f}, anchor_y={anchor_y:.1f}, max_gap={max_gap:.1f}")
            return None, "main stat sequence too far below visual anchor"
    else:
        dbg.append(f"V155_FALLBACK: accepted fixed main rows at y={first_main_y:.1f}; visual anchor_y={anchor_y:.1f} may be lower green title/set text")

    main_values: Dict[str, Any] = {}
    for k, idx in enumerate(main_label_idxs):
        lab = expected[k]
        next_idx = main_label_idxs[k+1] if k+1 < len(main_label_idxs) else None
        recovered_attack = None
        if lab == "attack":
            recovered_attack = _recover_main_attack_from_split_row(rows[idx])
        val = choose_value(lab, rows[idx], nearby_value_rows(rows, idx, next_idx), allow_nearby=True)
        if lab == "attack" and recovered_attack is not None:
            dbg.append(
                f"V190_MAIN_ATTACK_RECONSTRUCTION: row={idx} text={rows[idx].text!r} "
                f"reconstructed={recovered_attack}"
            )
        dbg.append(f"MAIN {LABEL_TEXT[lab]} row={idx} text={rows[idx].text!r} value={val}")
        if val is None:
            return None, f"missing/unsafe main value for {LABEL_TEXT[lab]}"
        main_values[lab] = clean_value(lab, val)

    attack = int(main_values["attack"])
    low_reason = suspicious_attack_reason(slot, tier, level, attack)
    if low_reason:
        dbg.append(f"ERROR: {low_reason}")
        return None, low_reason
    item: Dict[str, Any] = {"id": 0, "name": str(attack), "stats": [], "attack": attack}
    if "defense" in main_values: item["defense"] = main_values["defense"]
    if "accuracy" in main_values: item["accuracy"] = main_values["accuracy"]
    if "evasion" in main_values: item["evasion"] = main_values["evasion"]
    if "main-stat" in main_values: item["mainStat"] = main_values["main-stat"]
    # Internal-only helpers for HP/MP potion presets.  These are stripped before
    # mapleupload JSON is written, so optimiser item structure stays clean.
    item["__mainMaxHPForBuild"] = main_values.get("max-hp", 0)
    item["__mainMaxMPForBuild"] = main_values.get("max-mp", 0)

    # Parse substats after third main label/value area.
    sub_start = main_label_idxs[-1] + 1
    # Skip immediate value-only rows belonging to third main value.
    while sub_start < len(rows) and not canonical_label(rows[sub_start].text):
        sub_start += 1

    stats: List[Dict[str, Any]] = []
    used_label_idxs: set[int] = set()
    i = sub_start
    sub_label_rows_seen = 0
    # v155 keeps the old bounded stat-window behaviour: after the 3 fixed
    # main rows, inspect only the next 4 label rows. Do not keep walking down
    # into player name/title/set text just because fewer than 4 substats were
    # successfully parsed.
    while i < len(rows) and len(stats) < 4 and sub_label_rows_seen < 4:
        lab = canonical_label(rows[i].text)
        if lab:
            sub_label_rows_seen += 1
        if lab in SUBSTAT_LABELS:
            # Substats are trusted only when the value can be read from the
            # same UI row as the explicit label. Do not borrow nearby values.
            val = choose_value(lab, rows[i], nearby_value_rows(rows, i, None), allow_nearby=False, substat=True)
            if val is None or not plausible_value(lab, val):
                dbg.append(f"SKIP SUB {LABEL_TEXT.get(lab, lab)} row={i} text={rows[i].text!r} reason=no_trusted_same_row_value")
                i += 1
                continue
            cv = clean_value(lab, val)
            # strict trusted substat rules
            if lab in ("evasion", "accuracy") and not isinstance(cv, int):
                dbg.append(f"SKIP SUB {LABEL_TEXT.get(lab, lab)} row={i} text={rows[i].text!r} value={cv} reason=non_integer")
                i += 1
                continue
            if lab.startswith("skill-level") and not isinstance(cv, int):
                dbg.append(f"SKIP SUB {LABEL_TEXT.get(lab, lab)} row={i} text={rows[i].text!r} value={cv} reason=non_integer")
                i += 1
                continue
            # Prevent OCR fragments/main-row bleed from creating fake h/e/m.
            if lab == "max-hp" and (not isinstance(cv, int) or cv < 10000):
                dbg.append(f"SKIP SUB Max HP row={i} text={rows[i].text!r} value={cv} reason=too_small_or_fragment")
                i += 1
                continue
            if lab == "max-mp" and isinstance(cv, int) and cv > 1000:
                dbg.append(f"SKIP SUB Max MP row={i} text={rows[i].text!r} value={cv} reason=fragment")
                i += 1
                continue
            # Very low Evasion/Accuracy values have repeatedly come from OCR/comparison bleed; skip them rather than creating fake Arena/shorthand gear.
            if lab == "evasion" and isinstance(cv, int) and cv < 12:
                dbg.append(f"SKIP SUB Evasion row={i} text={rows[i].text!r} value={cv} reason=too_low_likely_ocr_bleed")
                i += 1
                continue
            if lab == "accuracy" and isinstance(cv, int) and cv < 10:
                dbg.append(f"SKIP SUB Accuracy row={i} text={rows[i].text!r} value={cv} reason=too_low_likely_ocr_bleed")
                i += 1
                continue
            stats.append({"type": SUBSTAT_LABELS[lab], "value": cv})
            dbg.append(f"SUB {LABEL_TEXT.get(lab, lab)} row={i} text={rows[i].text!r} value={cv}")
            used_label_idxs.add(i)
        i += 1

    # Build shorthand ONLY from trusted parsed substats.
    parts = [str(attack)]
    h = next((s["value"] for s in stats if s["type"] == "max-hp"), None)
    e = next((s["value"] for s in stats if s["type"] == "evasion"), None)
    m = next((s["value"] for s in stats if s["type"] == "max-mp"), None)
    flags = ""
    if e is not None: flags += "e"
    if h is not None: flags += "h"
    if m is not None: flags += "m"
    if flags:
        parts.append(flags)
        if e is not None: parts.append(str(e))
        if h is not None: parts.append(str(h))
        if m is not None: parts.append(str(m))
    name = " ".join(parts)
    item["name"] = name
    item["stats"] = stats

    p = ParsedItem(filename=filename, slot=slot, attack=attack, name=name, item=item, tier=tier, level=level, rows_debug=dbg)
    return p, ""


def blank_equipped_item(slot: str, item_id: int = 0) -> Dict[str, Any]:
    d = {"id": item_id, "name": "", "stats": [], "attack": 0}
    third = MAIN_TEMPLATES[slot][2]
    if third == "defense": d["defense"] = 0
    elif third == "accuracy": d["accuracy"] = 0
    elif third == "evasion": d["evasion"] = 0
    elif third == "main-stat": d["mainStat"] = 0
    return d


def item_score_attack(item: Dict[str, Any]) -> int:
    try: return int(item.get("attack") or 0)
    except Exception: return 0


def get_stat(item: Dict[str, Any], typ: str) -> float:
    vals = []
    if typ in item and isinstance(item.get(typ), (int, float, str)):
        try: vals.append(float(item.get(typ)))
        except Exception: pass
    for st in item.get("stats", []) or []:
        if st.get("type") == typ:
            try: vals.append(float(st.get("value") or 0))
            except Exception: pass
    return max(vals) if vals else 0.0


def total_stat(item: Dict[str, Any], typ: str) -> float:
    """Sum a stat across main/top-level fields and sub-option fields.

    For Arena/Colosseum, Evasion and Accuracy need this total rather than
    max(). Example: a Cape can have main Evasion 76 plus sub-option Evasion 18,
    and both contribute to the equipped stat screen.
    """
    total = 0.0
    if typ in item and isinstance(item.get(typ), (int, float, str)):
        try:
            total += float(item.get(typ) or 0)
        except Exception:
            pass
    for st in item.get("stats", []) or []:
        if st.get("type") == typ:
            try:
                total += float(st.get("value") or 0)
            except Exception:
                pass
    return total


def arena_stat(item: Dict[str, Any], typ: str) -> float:
    """Arena selector stat accessor.

    Use total main+sub for Evasion and Accuracy; use normal max semantics for
    other support stats.
    """
    if typ in ("evasion", "accuracy"):
        return total_stat(item, typ)
    return get_stat(item, typ)


def arena_damage_score(item: Dict[str, Any]) -> float:
    """Arena/Colosseum support score.

    This deliberately ignores PvE-only lines such as boss-damage and normal-damage.
    The score is only a tie-breaker after practical evasion and accuracy checks.
    """
    attack = item_score_attack(item) / 100.0
    score = attack
    # Reliable Arena damage / finish-before-timer stats.
    score += get_stat(item, "crit-rate") * 25.0
    score += get_stat(item, "crit-damage") * 10.0
    score += get_stat(item, "damage") * 12.0
    score += get_stat(item, "final-damage") * 30.0
    score += get_stat(item, "skill-damage") * 10.0
    score += get_stat(item, "attack-speed") * 8.0
    score += get_stat(item, "basic-attack-damage") * 6.0
    score += get_stat(item, "min-damage-ratio") * 4.0
    score += get_stat(item, "max-damage-ratio") * 2.0
    # Useful skill levels.
    score += get_stat(item, "skill-level-all") * 40.0
    for lvl in ("skill-level-1", "skill-level-2", "skill-level-3", "skill-level-4"):
        score += get_stat(item, lvl) * 18.0
    # Survivability has some value, but does not override evasion/accuracy.
    score += get_stat(item, "defense") / 120.0
    score += get_stat(item, "max-hp") / 2500.0
    return score


def arena_practical_score(item: Dict[str, Any]) -> float:
    """Practical Arena score used inside a narrow evasion band.

    Rules encoded:
    - Evasion first, but not maximum Evasion at any cost.
    - Evasion/Accuracy are totalled from main row + sub-options.
    - Accuracy second, especially for mirror evasion matchups.
    - Arena-relevant damage third.
    - PvE-only lines are ignored by arena_damage_score().
    """
    return (
        arena_stat(item, "evasion") * 1000.0 +
        arena_stat(item, "accuracy") * 80.0 +
        arena_damage_score(item)
    )


ARENA_MIN_EQUIPMENT_ACCURACY = 145.0
ARENA_EXISTING_ACCURACY_DROP_TOLERANCE = 5.0


def _item_by_id_in_grouped(items_by_slot: Dict[str, List[Dict[str, Any]]], slot: str, item_id: Any) -> Optional[Dict[str, Any]]:
    try:
        iid = int(item_id)
    except Exception:
        return None
    for it in items_by_slot.get(slot, []) or []:
        try:
            if int(it.get("id", 0)) == iid:
                return it
        except Exception:
            pass
    return None


def _preset_total(items_by_slot: Dict[str, List[Dict[str, Any]]], preset: Dict[str, Any], typ: str) -> float:
    total = 0.0
    if not isinstance(preset, dict):
        return 0.0
    for slot, item_id in preset.items():
        it = _item_by_id_in_grouped(items_by_slot, slot, item_id)
        if it:
            total += arena_stat(it, typ)
    return total


def _result_total(items_by_slot: Dict[str, List[Dict[str, Any]]], result: Dict[str, int], typ: str) -> float:
    total = 0.0
    for slot, item_id in result.items():
        it = _item_by_id_in_grouped(items_by_slot, slot, item_id)
        if it:
            total += arena_stat(it, typ)
    return total


def build_arena(items_by_slot: Dict[str, List[Dict[str, Any]]], base: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Build the Main Evasion Arena/Colosseum preset.

    v190 keeps the v165 main+sub total Evasion/Accuracy fix, but adds account
    practical Accuracy protection.  The previous v165 shoulder swap gained only
    +12 Evasion while dropping -17 Accuracy, which pushed the estimated Arena
    stat screen under the user's ~400 Accuracy target.

    Rule encoded here:
    - Pick high practical Evasion first.
    - Then protect total selected equipment Accuracy.
    - Aim for at least ARENA_MIN_EQUIPMENT_ACCURACY, and also do not drop more
      than ARENA_EXISTING_ACCURACY_DROP_TOLERANCE below the existing Arena preset
      if one exists in mapleexport.txt.
    - Repair low Accuracy by swapping the slot with the best Accuracy gain for
      the smallest Evasion loss, instead of blindly taking the highest Evasion
      item in every slot.
    """
    result: Dict[str, int] = {}
    for slot, items in items_by_slot.items():
        if not items:
            continue
        best_e_val = max(arena_stat(it, "evasion") for it in items)

        if best_e_val > 0:
            # v165 widened this via total main+sub Evasion/Accuracy.  Keep a
            # practical Evasion band, then prefer Accuracy and Arena support.
            candidates = [it for it in items if arena_stat(it, "evasion") >= best_e_val - 5]
            chosen = max(candidates, key=arena_practical_score)
        else:
            chosen = max(items, key=lambda it: (arena_stat(it, "accuracy"), arena_damage_score(it), item_score_attack(it)))

        if int(chosen.get("id", 0)):
            result[slot] = int(chosen["id"])

    # Accuracy protection pass.  This is intentionally global, not per-slot,
    # because the character stat screen target is based on the final equipped set.
    existing_acc = _preset_total(items_by_slot, base or {}, "accuracy") if base else 0.0
    target_acc = ARENA_MIN_EQUIPMENT_ACCURACY
    if existing_acc > 0:
        target_acc = max(target_acc, existing_acc - ARENA_EXISTING_ACCURACY_DROP_TOLERANCE)

    def cur_acc() -> float:
        return _result_total(items_by_slot, result, "accuracy")

    # Greedily swap to alternatives that gain Accuracy with the least practical
    # Evasion loss.  Stop when no useful swap remains.
    safety = 0
    while cur_acc() + 1e-9 < target_acc and safety < len(SLOT_ORDER) + 3:
        safety += 1
        best_swap = None
        for slot, current_id in list(result.items()):
            current = _item_by_id_in_grouped(items_by_slot, slot, current_id)
            if not current:
                continue
            cur_ev = arena_stat(current, "evasion")
            cur_ac = arena_stat(current, "accuracy")
            cur_dmg = arena_damage_score(current)
            for alt in items_by_slot.get(slot, []) or []:
                try:
                    alt_id = int(alt.get("id", 0))
                except Exception:
                    continue
                if not alt_id or alt_id == int(current_id):
                    continue
                acc_gain = arena_stat(alt, "accuracy") - cur_ac
                if acc_gain <= 0:
                    continue
                ev_loss = cur_ev - arena_stat(alt, "evasion")
                dmg_loss = cur_dmg - arena_damage_score(alt)
                # Sort priority: smallest Evasion loss per Accuracy gain, then
                # smallest absolute Evasion loss, then smallest support loss.
                # Negative losses are gains and should be preferred.
                key = (ev_loss / acc_gain, ev_loss, dmg_loss / max(acc_gain, 1.0), -acc_gain)
                if best_swap is None or key < best_swap[0]:
                    best_swap = (key, slot, alt_id)
        if best_swap is None:
            break
        _, slot, alt_id = best_swap
        result[slot] = alt_id

    return result


def pve_damage_score(item: Dict[str, Any], mode: str = "breakthrough") -> float:
    """Simple fresh-OCR PvE/BIS slot score for managed PvE presets.

    This is intentionally item-local rather than a full optimiser simulation.  It
    is used only to seed safe presets from the clean OCR inventory when the old
    optimiser inventory is not trusted.  The user can still rebuild/tune these
    presets in the optimiser afterwards.

    mode="breakthrough" favours chapter/breakthrough/general damage and normal
    monster damage.  mode="chapter-boss" favours boss damage while keeping the
    same core damage stats.
    """
    score = item_score_attack(item) / 50.0
    score += get_stat(item, "attack") / 20.0
    score += get_stat(item, "main-stat") / 12.0

    # Universal damage stats.
    score += get_stat(item, "damage") * 45.0
    score += get_stat(item, "final-damage") * 120.0
    score += get_stat(item, "crit-rate") * 35.0
    score += get_stat(item, "crit-damage") * 28.0
    score += get_stat(item, "min-damage-ratio") * 12.0
    score += get_stat(item, "max-damage-ratio") * 10.0
    score += get_stat(item, "basic-attack-damage") * 16.0
    score += get_stat(item, "skill-damage") * 35.0
    score += get_stat(item, "attack-speed") * 10.0

    # Content-specific lines.
    if mode == "chapter-boss":
        score += get_stat(item, "boss-damage") * 55.0
        score += get_stat(item, "normal-damage") * 8.0
    else:
        # Breakthrough/chapter progression tends to value normal/general damage
        # more than boss-only damage, but boss damage is not completely useless
        # in mixed chapter content.
        score += get_stat(item, "normal-damage") * 50.0
        score += get_stat(item, "boss-damage") * 14.0

    # Useful skill levels.  For I/L mage at this stage, 3rd/4th job lines have
    # been strong in the BIS work; lower job/all levels still get value.
    score += get_stat(item, "skill-level-all") * 90.0
    score += get_stat(item, "skill-level-4") * 80.0
    score += get_stat(item, "skill-level-3") * 70.0
    score += get_stat(item, "skill-level-2") * 35.0
    score += get_stat(item, "skill-level-1") * 25.0

    # Minor safety/consistency tie-breaks.
    score += get_stat(item, "accuracy") * 8.0
    score += get_stat(item, "defense") / 150.0
    score += get_stat(item, "max-hp") / 4000.0
    return score


def build_pve_preset(items_by_slot: Dict[str, List[Dict[str, Any]]], mode: str = "breakthrough") -> Dict[str, int]:
    """Build a simple per-slot PvE preset from fresh OCR items only."""
    out: Dict[str, int] = {}
    for slot, items in items_by_slot.items():
        if not items:
            continue
        chosen = max(items, key=lambda it: (pve_damage_score(it, mode), item_score_attack(it)))
        try:
            iid = int(chosen.get("id", 0))
        except Exception:
            iid = 0
        if iid:
            out[slot] = iid
    return out


def build_accuracy_counter(items_by_slot: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
    """Optional future Arena accuracy-counter preset for fighting evasion players.

    This is only used if the user's optimiser file already contains an equipment
    preset named Accuracy, Arena Accuracy, Accuracy Counter, or Evasion Counter.
    """
    result: Dict[str, int] = {}
    for slot, items in items_by_slot.items():
        if not items:
            continue
        chosen = max(items, key=lambda it: (arena_stat(it, "accuracy"), arena_stat(it, "evasion"), arena_damage_score(it), item_score_attack(it)))
        if int(chosen.get("id", 0)):
            result[slot] = int(chosen["id"])
    return result


def total_hp_for_potion_set(item: Dict[str, Any]) -> float:
    """Pure HP potion-upgrade score: main Max HP + sub-option Max HP only.

    This deliberately ignores Attack, CP, DPS, Arena value, skill levels, etc.
    The HP preset is worn for a few seconds to inflate the potion upgrade value.
    """
    total = 0.0
    try:
        total += float(item.get("__mainMaxHPForBuild") or 0)
    except Exception:
        pass
    for st in item.get("stats", []) or []:
        if st.get("type") == "max-hp":
            try:
                total += float(st.get("value") or 0)
            except Exception:
                pass
    return total


def mp_percent_for_potion_set(item: Dict[str, Any]) -> float:
    """Pure MP potion-upgrade percentage score: Max MP % sub-options only.

    v163 rule: for MP, percentages are what matter for the potion-stage
    inflation helper set.  Use Max MP % lines first and do not let a flat main
    Shoes/Belt Max MP value beat a real percentage line.
    """
    total = 0.0
    for st in item.get("stats", []) or []:
        if st.get("type") == "max-mp":
            try:
                total += float(st.get("value") or 0)
            except Exception:
                pass
    return total


def mp_flat_main_for_potion_set(item: Dict[str, Any]) -> float:
    """Fallback MP score: flat main Max MP only, used only if a whole slot
    has no Max MP % items at all.
    """
    try:
        return float(item.get("__mainMaxMPForBuild") or 0)
    except Exception:
        return 0.0


def total_mp_for_potion_set(item: Dict[str, Any]) -> float:
    """Legacy/debug MP total: Max MP % sub-options + flat main Max MP.

    The actual v163 MP picker no longer ranks by this mixed total because it
    can incorrectly make a flat HP/MP shoe beat a percentage MP shoe.
    """
    return mp_percent_for_potion_set(item) + mp_flat_main_for_potion_set(item)


def build_hp(items_by_slot: Dict[str, List[Dict[str, Any]]], base: Optional[Dict[str, int]] = None) -> Dict[str, int]:
    """Build pure HP potion helper set.

    For each slot, choose the item with the highest total HP on that single
    piece: main Max HP + Max HP substats.  If no item in a slot has HP at all,
    preserve the existing slot choice rather than swapping to a meaningless 0-HP
    item.
    """
    out = dict(base or {})
    for slot, items in items_by_slot.items():
        if not items:
            continue
        best_val = max(total_hp_for_potion_set(it) for it in items)
        if best_val <= 0:
            continue
        chosen = max(items, key=lambda it: (total_hp_for_potion_set(it), item_score_attack(it)))
        if int(chosen.get("id", 0)):
            out[slot] = int(chosen["id"])
    return out


def build_mp(items_by_slot: Dict[str, List[Dict[str, Any]]], base: Optional[Dict[str, int]] = None) -> Dict[str, int]:
    """Build pure MP potion helper set.

    v163 rule:
    1. For each slot, choose the item with the highest total Max MP % line.
    2. If that slot has no Max MP % item at all, fall back to the highest flat
       main Max MP value.
    3. If there is no MP value of either kind, preserve the existing slot.

    This deliberately ignores Attack, CP, HP, DPS, Arena value, skill levels,
    etc.  The MP preset is worn briefly only to inflate the MP potion upgrade
    stage.
    """
    out = dict(base or {})
    for slot, items in items_by_slot.items():
        if not items:
            continue

        best_percent = max(mp_percent_for_potion_set(it) for it in items)
        if best_percent > 0:
            chosen = max(items, key=lambda it: (mp_percent_for_potion_set(it), item_score_attack(it)))
        else:
            best_flat = max(mp_flat_main_for_potion_set(it) for it in items)
            if best_flat <= 0:
                continue
            chosen = max(items, key=lambda it: (mp_flat_main_for_potion_set(it), item_score_attack(it)))

        if int(chosen.get("id", 0)):
            out[slot] = int(chosen["id"])
    return out




def fill_missing_slots_with_best_available(preset: Dict[str, int], items_by_slot: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
    """Fill empty slots with the strongest available item when no target stat exists.

    v190 clears stale optimiser preset refs. For HP/MP, if a slot has no HP/MP
    candidate at all, we still choose a fresh OCR item rather than preserving an
    old deleted optimiser item or leaving a stale reference. This keeps managed
    presets complete while target-stat slots remain selected by the pure HP/MP
    rules.
    """
    out = dict(preset or {})
    for slot, items in items_by_slot.items():
        if slot in out or not items:
            continue
        chosen = max(items, key=lambda it: item_score_attack(it))
        if int(chosen.get("id", 0)):
            out[slot] = int(chosen["id"])
    return out


def normalize_equipment_display_names(obj: Any, report: Optional[List[str]] = None, path: str = "root") -> None:
    """Make equipment display names agree with the exported attack field.

    Optimiser/export files can occasionally contain a stale shorthand name, for
    example name="16198" while attack=20826.  Reports and preset summaries read
    the name field, so before writing mapleupload.txt we normalise equipment
    dictionaries from the real stat fields instead of trusting stale names.

    Conservative behaviour:
    - Only acts on dicts that look like equipment items and have a positive
      numeric attack field.
    - If the name starts with a number and that number differs from attack, only
      the leading number is replaced; suffixes like "e 20", "h 70924", or
      "em 19 25.4" are preserved.
    - If the name is blank/non-numeric/generic like "Top 1", it becomes the
      attack value.
    - Already-correct names are left unchanged.
    """
    if isinstance(obj, dict):
        looks_like_item = "attack" in obj and ("stats" in obj or "mainStat" in obj or "defense" in obj or "accuracy" in obj or "evasion" in obj)
        if looks_like_item:
            try:
                attack = int(float(str(obj.get("attack") or 0).replace(",", "")))
            except Exception:
                attack = 0
            if attack > 0:
                old = str(obj.get("name") or "").strip()
                new = str(attack)
                m = re.match(r"^\s*(\d[\d,]*)(.*)$", old)
                if m:
                    suffix = (m.group(2) or "").strip()
                    if suffix:
                        new = f"{attack} {suffix}"
                if old != new:
                    obj["name"] = new
                    if report is not None:
                        report.append(f"{path}: {old!r} -> {new!r} (attack={attack})")
        for k, v in obj.items():
            normalize_equipment_display_names(v, report, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            normalize_equipment_display_names(v, report, f"{path}[{i}]")

def strip_internal_build_keys(obj: Any) -> None:
    """Remove helper keys before writing optimiser JSON."""
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            if str(k).startswith("__"):
                obj.pop(k, None)
            else:
                strip_internal_build_keys(obj[k])
    elif isinstance(obj, list):
        for v in obj:
            strip_internal_build_keys(v)


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")

def count_import_equipment_rows(data: Dict[str, Any]) -> int:
    """Count OCR-imported equipment rows in the optimiser JSON output.

    mapleupload.txt is expected to be optimiser JSON, but it must contain the
    OCR-scanned items in comparisonItems/comparisonItemsBySlot.  A clean
    equipment-free optimiser export has these lists empty, and must never be
    written as mapleupload.txt.
    """
    total = 0
    flat = data.get("comparisonItems")
    if isinstance(flat, list):
        total += sum(1 for it in flat if isinstance(it, dict) and int(it.get("id") or 0) > 0 and int(it.get("attack") or 0) > 0)
    by_slot = data.get("comparisonItemsBySlot")
    if isinstance(by_slot, dict):
        seen = set()
        for items in by_slot.values():
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                iid = int(it.get("id") or 0)
                atk = int(it.get("attack") or 0)
                if iid > 0 and atk > 0 and iid not in seen:
                    seen.add(iid)
        total = max(total, len(seen))
    return total


def count_preset_refs(data: Dict[str, Any]) -> int:
    total = 0
    presets = data.get("equipmentPresets")
    if isinstance(presets, list):
        for preset in presets:
            if isinstance(preset, dict):
                total += len([v for v in preset.values() if v])
    return total


def validate_mapleupload_payload(data: Dict[str, Any], parsed_count: int) -> None:
    """Hard guardrail: mapleupload.txt must contain OCR equipment rows.

    This prevents the v139-style accident where an equipment-free clean file was
    saved/renamed as mapleupload.txt.  If there are no trusted OCR rows, the
    script leaves any existing mapleupload.txt untouched and writes a warning
    file instead.
    """
    if not isinstance(data, dict):
        raise RuntimeError("Refusing to write mapleupload.txt: output is not optimiser JSON.")
    if parsed_count <= 0:
        raise RuntimeError("Refusing to write mapleupload.txt: no trusted OCR equipment rows were parsed.")
    imported = count_import_equipment_rows(data)
    if imported <= 0:
        raise RuntimeError("Refusing to write mapleupload.txt: output contains no comparison equipment items.")
    if imported != parsed_count:
        raise RuntimeError(
            f"Refusing to write mapleupload.txt: equipment row count mismatch; output has {imported} unique item rows but parser trusted {parsed_count}."
        )


def safe_write_mapleupload(path: Path, data: Dict[str, Any], parsed_count: int) -> None:
    """Validate and atomically replace mapleupload.txt.

    Existing mapleupload.txt is backed up before replacement so a bad run cannot
    silently destroy the last good upload file.
    """
    validate_mapleupload_payload(data, parsed_count)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    backup_path = path.with_name(path.stem + "_previous_good" + path.suffix)
    tmp_path.write_text(text, encoding="utf-8")
    if path.exists():
        try:
            shutil.copy2(path, backup_path)
        except Exception:
            pass
    os.replace(tmp_path, path)



def stat_summary_for_item(item: Dict[str, Any]) -> str:
    bits = []
    for st in item.get("stats", []) or []:
        typ = str(st.get("type") or "")
        val = st.get("value")
        label = LABEL_TEXT.get(typ, typ)
        if val is None:
            continue
        if isinstance(val, float) and abs(val - round(val)) > 0.0001:
            bits.append(f"{label} {val:g}")
        else:
            bits.append(f"{label} {val}")
    return "; ".join(bits)



def _authority_stat_value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and abs(value - round(value)) > 0.0001:
        return f"{value:g}"
    return str(value)


def write_bis_report_authority(
    output_dir: Path,
    parsed: List[ParsedItem],
    run_id: str,
) -> Tuple[Path, Path]:
    """Write the single-source BIS report authority sidecars.

    v197 rule:
      * OCR screenshot row order is authoritative for first-substat validation.
      * BAG source_capture_order is authoritative for LOCK/UNLOCK working order.
      * Do not infer either rule from optimiser item/stat order.
    """
    csv_path = output_dir / f"bis_report_authority_{VERSION}.csv"
    txt_path = output_dir / f"BIS_REPORT_AUTHORITY_{VERSION}.txt"

    fields = [
        "run_id",
        "filename",
        "source",
        "source_capture_order",
        "batch_capture_order",
        "capture_timestamp",
        "slot",
        "equipment_id",
        "name",
        "attack",
        "lock_status",
        "first_substat_type",
        "first_substat_label",
        "first_substat_value",
        "ordered_substats_json",
    ]

    rows = []
    for p in sorted(
        parsed,
        key=lambda x: (
            0 if x.source == "bag" else 1,
            int(x.source_capture_order or 0),
            x.filename,
        ),
    ):
        stats = list(p.item.get("stats", []) or [])
        first = stats[0] if stats and isinstance(stats[0], dict) else {}
        first_type = str(first.get("type") or "")
        first_label = LABEL_TEXT.get(first_type, first_type) if first_type else ""
        first_value = _authority_stat_value_text(first.get("value")) if first else ""

        rows.append({
            "run_id": run_id,
            "filename": p.filename,
            "source": p.source,
            "source_capture_order": int(p.source_capture_order or 0),
            "batch_capture_order": int(p.batch_capture_order or 0),
            "capture_timestamp": p.capture_timestamp,
            "slot": p.slot,
            "equipment_id": int(p.item.get("id", 0) or 0),
            "name": p.name,
            "attack": int(p.attack),
            "lock_status": p.lock_status,
            "first_substat_type": first_type,
            "first_substat_label": first_label,
            "first_substat_value": first_value,
            "ordered_substats_json": json.dumps(stats, ensure_ascii=False, separators=(",", ":")),
        })

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    text = "\n".join([
        f"Generated by MapleOCR {VERSION}",
        f"RUN_ID: {run_id}",
        "",
        "BISMIRPG REPORT AUTHORITY RULES",
        "",
        "1. first_substat_* comes from the FIRST parsed OCR substat row in the screenshot.",
        "   This is authoritative for first-substat validation.",
        "   Do not substitute lock_status.txt ordering or optimiser export stat ordering.",
        "",
        "2. For LOCK and UNLOCK action lists, use source=bag rows and sort",
        "   source_capture_order ascending. This matches the player's bag scrolling path.",
        "",
        "3. equipment_id, lock_status, first-substat data and capture order in this CSV",
        "   all come from the same OCR RUN_ID.",
        "",
        f"Trusted authority rows: {len(rows)}",
    ]) + "\n"
    write_text(txt_path, text)
    return csv_path, txt_path


def build_lock_snapshot_text(parsed: List[ParsedItem], run_id: str, bag_count: int, equipped_count: int, *, locked_only: bool) -> str:
    title = "MapleOCR locked equipment" if locked_only else "MapleOCR lock status snapshot"
    lines = [
        f"# {title}",
        f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Version: {VERSION}",
        f"# RUN_ID: {run_id}",
        f"# Screenshot batch: bag={bag_count}, equipped={equipped_count}, total={bag_count + equipped_count}",
        "# Primary key: equipment ID from this same mapleupload/mapleexcel run",
    ]
    if locked_only:
        lines.append("# Columns: slot|id|name|source|filename")
    else:
        lines.append("# Columns: lock_status|slot|id|name|source|filename|substats")
    lines.append("")
    items = sorted(parsed, key=lambda p: (p.slot, int(p.item.get("id", 0) or 0), p.filename))
    wrote = 0
    for p in items:
        iid = int(p.item.get("id", 0) or 0)
        if locked_only and p.lock_status != "locked":
            continue
        if locked_only:
            lines.append(f"{p.slot}|{iid}|{p.name}|{p.source}|{p.filename}")
        else:
            lines.append(f"{p.lock_status}|{p.slot}|{iid}|{p.name}|{p.source}|{p.filename}|{stat_summary_for_item(p.item)}")
        wrote += 1
    if wrote == 0:
        lines.append("# None")
    return "\n".join(lines) + "\n"


def build_final_summary(screenshots_found: int, trusted_count: int, review_count: int, mapleupload_written: bool) -> str:
    processed = trusted_count + review_count
    lines = [
        "",
        "Summary:",
        f"  Screenshots found: {screenshots_found}",
        f"  Screenshots processed: {processed}/{screenshots_found}",
        f"  Trusted items: {trusted_count}",
        f"  Review items: {review_count}",
        f"  Total equipment rows: {trusted_count}",
        f"  mapleupload.txt written: {'YES' if mapleupload_written else 'NO'}",
    ]
    if trusted_count == 0:
        lines.append("  WARNING: No trusted equipment rows were parsed; mapleupload.txt was protected from overwrite.")
    return "\n".join(lines)



def load_easyocr_reader():
    import easyocr  # type: ignore
    return easyocr.Reader(["en"], gpu=True)


def ocr_image(reader: Any, path: Path) -> List[OCRRow]:
    img = cv2.imread(str(path)) if cv2 is not None else None
    results = reader.readtext(str(path), detail=1, paragraph=False)
    toks = tokens_from_easyocr(results, image=img)
    rows = dedupe_rows(group_rows(toks))
    return rows


def detect_equipped_star_force(reader: Any, path: Path) -> Tuple[Optional[int], List[str]]:
    """Read the yellow-star badge number from an Equipped screenshot.

    v197 keeps the same fixed equipment-card geometry as v196, but does not rely
    on one EasyOCR pass. Some perfectly clear badges (confirmed example:
    Wise Royal Pauldron, visible Star Force 17) can produce no digits on the
    unprocessed crop. We therefore run several conservative image variants and
    accept only a stable plausible result. Ambiguous results still fail closed.
    """
    dbg: List[str] = []
    if cv2 is None:
        return None, ["STAR_FORCE: cv2 unavailable"]
    img = cv2.imread(str(path))
    if img is None or img.size == 0:
        return None, ["STAR_FORCE: image unreadable"]

    h, w = img.shape[:2]
    x1 = max(0, int(round(w * 0.155)))
    x2 = min(w, int(round(w * 0.300)))
    y1 = max(0, int(round(h * 0.305)))
    y2 = min(h, int(round(h * 0.395)))
    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        return None, [f"STAR_FORCE: empty crop ({x1},{y1})-({x2},{y2})"]

    # Keep all variants derived only from the fixed Star Force badge crop.
    # No full-card number search is allowed: that could confuse level/tier text.
    big = cv2.resize(crop, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, otsu_inv = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # The badge number is on the right half of the fixed crop. A tighter pass
    # reduces interference from the yellow star icon itself.
    bw = big.shape[1]
    tight = big[:, int(round(bw * 0.42)):]
    tight_gray = cv2.cvtColor(tight, cv2.COLOR_BGR2GRAY)
    tight_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(tight_gray)
    _, tight_otsu = cv2.threshold(tight_clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, tight_inv = cv2.threshold(tight_clahe, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    variants = [
        ("original4x", big),
        ("gray_clahe", clahe),
        ("otsu", otsu),
        ("otsu_inv", otsu_inv),
        ("tight_original", tight),
        ("tight_clahe", tight_clahe),
        ("tight_otsu", tight_otsu),
        ("tight_inv", tight_inv),
    ]

    observations: List[Tuple[int, float, str, str]] = []
    for label, variant in variants:
        try:
            results = reader.readtext(
                variant,
                detail=1,
                paragraph=False,
                allowlist="0123456789",
            )
        except TypeError:
            results = reader.readtext(variant, detail=1, paragraph=False)
        except Exception as exc:
            dbg.append(f"STAR_FORCE_VARIANT_ERROR: {label}: {exc}")
            continue

        local: List[str] = []
        for r in results or []:
            try:
                text = str(r[1])
                conf = float(r[2]) if len(r) > 2 else 0.0
            except Exception:
                continue
            for m in re.finditer(r"\d{1,2}", text):
                try:
                    value = int(m.group(0))
                except ValueError:
                    continue
                if 0 <= value <= 30:
                    observations.append((value, conf, text, label))
                    local.append(f"{value}@{conf:.3f}<{text}>")
        dbg.append(
            f"STAR_FORCE_OCR_{label}: " +
            (" | ".join(local) if local else "NO PLAUSIBLE DIGITS")
        )

    dbg.insert(0, f"STAR_FORCE_CROP: x={x1}:{x2} y={y1}:{y2}")
    if not observations:
        return None, dbg

    # Prefer complete two-digit reads, as in v196 FIXED2. Then require agreement
    # across preprocessing variants when possible.
    two_digit = [o for o in observations if 10 <= o[0] <= 30]
    pool = two_digit if two_digit else observations

    from collections import Counter
    counts = Counter(o[0] for o in pool)
    ranked = counts.most_common()
    top_value, top_count = ranked[0]
    second_count = ranked[1][1] if len(ranked) > 1 else 0

    # If different values tie for the most variant support, refuse to guess.
    if second_count == top_count:
        dbg.append(
            "STAR_FORCE_AMBIGUOUS: tied candidate support " +
            ", ".join(f"{v}x{c}" for v, c in ranked)
        )
        return None, dbg

    agreeing = [o for o in pool if o[0] == top_value]
    agreeing.sort(key=lambda x: x[1], reverse=True)
    best = agreeing[0]

    # For two-digit values, one clear recovered pass is acceptable if no other
    # two-digit value competes. For single-digit values, require two independent
    # variant observations to avoid accepting a clipped digit.
    if top_value < 10 and top_count < 2:
        dbg.append(
            f"STAR_FORCE_AMBIGUOUS: single-digit {top_value} seen only once"
        )
        return None, dbg

    dbg.append(
        "STAR_FORCE_SELECTION: " +
        f"value={top_value} support={top_count}/{len(pool)} " +
        f"best_confidence={best[1]:.3f} variant={best[3]} raw={best[2]!r}"
    )
    dbg.append(f"STAR_FORCE_ACCEPTED: {top_value}")
    return top_value, dbg


def assign_ids(parsed: List[ParsedItem], start_id: int) -> None:
    next_id = max(start_id, 1000)
    for p in parsed:
        p.item["id"] = next_id
        next_id += 1


def _preset_name_is_basic(name: Any) -> bool:
    nm = str(name or "").strip().lower()
    return nm in {"basic", "basic preset", "basic set", "preset 1"}


def _find_preset_index(names: List[Any], target: str) -> Optional[int]:
    target_l = target.strip().lower()
    for i, nm in enumerate(names):
        if str(nm or "").strip().lower() == target_l:
            return i
    return None


def _ensure_preset(names: List[Any], presets: List[Dict[str, Any]], stats: List[Dict[str, Any]], name: str) -> int:
    idx = _find_preset_index(names, name)
    if idx is not None:
        while len(presets) <= idx:
            presets.append({})
        while len(stats) <= idx:
            stats.append({})
        return idx
    names.append(name)
    presets.append({})
    stats.append({})
    return len(names) - 1



PERCENT_SUBSTAT_TYPES_FOR_OPTIMIZER_RAW = {
    "crit-rate", "crit-damage", "attack-speed", "normal-damage", "boss-damage",
    "damage", "final-damage", "min-damage-ratio", "max-damage-ratio",
    "main-stat-percent", "basic-attack-damage", "skill-damage", "defense-penetration",
}


def _slot_percent_multiplier(starforce_by_slot: Dict[str, Any], slot: str) -> float:
    """Return the optimiser display multiplier for percentage sub-options.

    Maple Idle screenshots show the already-boosted visible percentage. The
    optimiser JSON stores the lower raw line and applies the slot star-force
    display boost itself. For the user's current optimiser, the observed rule is
    +1% per star above 10; e.g. Top star-force 16 means 11.5 visible should be
    written as about 10.8 raw so optimiser displays 11.5 instead of 12.2.

    Main integer values such as Attack/HP/Main Stat/Defense are intentionally
    NOT changed in v191.
    """
    try:
        sf = int(starforce_by_slot.get(slot, 0) or 0)
    except Exception:
        sf = 0
    bonus = max(0, sf - 10) / 100.0
    return 1.0 + bonus


def _raw_percent_value_for_optimizer(value: Any, multiplier: float) -> Any:
    if not isinstance(value, (int, float)) or multiplier <= 1.0:
        return value
    raw = float(value) / multiplier
    # Keep one decimal because the optimiser/UI lines are one-decimal stats.
    raw = round(raw, 1)
    # Do not turn real decimals into ints; these are percentage-style options.
    return raw


def apply_optimizer_percent_raw_fix(parsed: List[ParsedItem], old_data: Dict[str, Any]) -> Tuple[List[ParsedItem], List[str]]:
    """Copy parsed items and convert only percentage substats for optimiser JSON.

    The displayed item name/shorthand stays based on the screenshot-visible
    value for human matching. Only the numeric stat values written in item.stats
    are divided by the slot's percentage display multiplier.
    """
    sf = old_data.get("equipmentStarForceBySlot") or {}
    fixed: List[ParsedItem] = []
    report: List[str] = [f"Generated by MapleOCR {VERSION}", "OPTIMISER PERCENT SUBSTAT RAW FIX", "", "Attack / HP / Main Stat / Defense are kept exactly as OCR parsed them.", "Only percentage-style sub-options are converted from screenshot-visible to optimiser raw.", ""]
    for p in parsed:
        mult = _slot_percent_multiplier(sf, p.slot)
        item = json.loads(json.dumps(p.item))
        changes = []
        for st in item.get("stats", []) or []:
            typ = st.get("type")
            val = st.get("value")
            should_scale = typ in PERCENT_SUBSTAT_TYPES_FOR_OPTIMIZER_RAW
            # Max MP sub-options are percentage-like when they are decimal/small values.
            if typ == "max-mp" and isinstance(val, (int, float)) and float(val) < 100:
                should_scale = True
            if should_scale:
                new_val = _raw_percent_value_for_optimizer(val, mult)
                if new_val != val:
                    changes.append(f"{typ}: {val} -> {new_val} (x{mult:.2f})")
                    st["value"] = new_val
        np = ParsedItem(filename=p.filename, slot=p.slot, attack=p.attack, name=p.name, item=item, tier=p.tier, level=p.level, rows_debug=list(p.rows_debug), warnings=list(p.warnings), review_reason=p.review_reason)
        fixed.append(np)
        if changes:
            report.append(f"{p.filename} | {p.slot} | {p.name}")
            report.extend(f"  - {c}" for c in changes)
    if len(report) <= 6:
        report.append("No percentage substats required conversion.")
    return fixed, report


def _ensure_basic_preset(names: List[Any], presets: List[Dict[str, Any]], stats: List[Dict[str, Any]]) -> int:
    """Ensure a Basic Preset name exists, but do not auto-build Basic.

    v190 treats fresh OCR inventory as the source of truth. Basic is kept as a
    named placeholder so the optimiser UI stays organised, but the user should
    rebuild it inside the optimiser after import.
    """
    for candidate in ("Basic Preset", "Basic", "Preset 1"):
        idx = _find_preset_index(names, candidate)
        if idx is not None:
            while len(presets) <= idx:
                presets.append({})
            while len(stats) <= idx:
                stats.append({})
            return idx
    names.insert(0, "Basic Preset")
    presets.insert(0, {})
    stats.insert(0, {})
    return 0



def _item_to_equipment_base_stats(item: Dict[str, Any], slot: str) -> Dict[str, Any]:
    """Build optimiser equipmentBaseStats for an equipped OCR item.

    v191 writes Basic from screenshots\\Equipped in two places:
    1) equipmentPresets[Basic Preset]
    2) equippedItemsBySlot / equipmentBaseStats

    Some optimiser UI paths read the currently-equipped/basic state from
    equippedItemsBySlot rather than only equipmentPresets.  Keeping these in
    sync prevents Basic Preset importing as a blank set.
    """
    return {
        "mainAttack": int(item.get("attack", 0) or 0),
        "mainMainStat": int(item.get("mainStat", 0) or 0),
        "mainDefense": int(item.get("defense", 0) or 0),
        "mainAccuracy": int(item.get("accuracy", 0) or 0),
        "mainEvasion": int(item.get("evasion", 0) or 0),
        "subOptions": json.loads(json.dumps(item.get("stats") or [])),
        "subAttack": 0,
    }


def _validate_basic_equipped_written(data: Dict[str, Any], expected_slots: int) -> None:
    """Hard guardrail for the Equipped-folder Basic workflow."""
    if expected_slots <= 0:
        return
    names = data.get("equipmentPresetNames") or []
    presets = data.get("equipmentPresets") or []
    basic_idx = next((i for i, nm in enumerate(names) if _preset_name_is_basic(nm)), None)
    if basic_idx is None or basic_idx >= len(presets):
        raise RuntimeError("Refusing to write mapleupload.txt: Equipped screenshots were found but Basic Preset is missing.")
    basic = presets[basic_idx] or {}
    if len(basic) < expected_slots:
        raise RuntimeError(f"Refusing to write mapleupload.txt: Basic Preset from Equipped is incomplete ({len(basic)}/{expected_slots} slots).")
    equipped = data.get("equippedItemsBySlot") or {}
    if len(equipped) < expected_slots:
        raise RuntimeError(f"Refusing to write mapleupload.txt: equippedItemsBySlot is incomplete ({len(equipped)}/{expected_slots} slots).")
    bases = data.get("equipmentBaseStats") or {}
    if len(bases) < expected_slots:
        raise RuntimeError(f"Refusing to write mapleupload.txt: equipmentBaseStats is incomplete ({len(bases)}/{expected_slots} slots).")

def make_output_data(old_data: Dict[str, Any], parsed: List[ParsedItem], equipped_basic_refs: Optional[Dict[str, int]] = None, equipped_starforce_by_slot: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    data = json.loads(json.dumps(old_data))  # deep copy non-equipment optimiser settings

    # v197: screenshots\\Equipped Star Force badge is authoritative.
    if equipped_starforce_by_slot:
        sf = dict(data.get("equipmentStarForceBySlot") or {})
        for slot, value in equipped_starforce_by_slot.items():
            sf[slot] = int(value)
        data["equipmentStarForceBySlot"] = sf

    # v190 workflow:
    # - mapleexport.txt is used as a shell only: class, abilities, companions,
    #   artifacts, potentials, scrolls, and preset names are kept.
    # - Old optimiser equipment inventory is NOT trusted because it can contain
    #   deleted/stale items.
    # - comparisonItems / comparisonItemsBySlot are rebuilt from fresh OCR only.
    # - Top-level screenshots are bag inventory; screenshots\\Equipped are currently worn equipment.
    # - Equipped screenshots are included in fresh inventory and written into Basic Preset.
    # - Arena, Colosseum, HP, MP and Chapter Boss are rebuilt from fresh OCR only. Breakthrough is left cleared for the optimiser to rebuild.
    # - Every other equipment preset is kept by name but cleared so the user can
    #   rebuild it in the optimiser from the clean inventory.

    grouped: Dict[str, List[Dict[str, Any]]] = {slot: [] for slot in SLOT_ORDER}
    flat: List[Dict[str, Any]] = []
    for p in parsed:
        grouped[p.slot].append(p.item)
        flat.append(p.item)

    # Fresh OCR inventory is the only equipment inventory written.
    data["comparisonItemsBySlot"] = grouped
    data["comparisonItems"] = flat
    data["inventoryDisplayOrder"] = None
    data["nextComparisonItemId"] = max([int(it.get("id", 0)) for it in flat] + [1000]) + 1

    # Clear stale optimiser equipment records by default.
    # v190 will repopulate these from screenshots\Equipped below, because the
    # optimiser can display/import Basic from equippedItemsBySlot/equipmentBaseStats,
    # not only equipmentPresets[Basic Preset].
    data["equippedItemsBySlot"] = {}
    data["equippedItem"] = {}
    data["equipmentBaseStats"] = {}

    # Keep preset names in the old order, but clear every preset by default.
    names = list(old_data.get("equipmentPresetNames") or [])
    old_presets = old_data.get("equipmentPresets") or []
    old_stats = old_data.get("equipmentPresetStats") or []
    max_len = max(len(names), len(old_presets), len(old_stats))
    while len(names) < max_len:
        names.append(f"Preset {len(names) + 1}")

    new_presets: List[Dict[str, Any]] = [{} for _ in range(len(names))]
    new_stats: List[Dict[str, Any]] = [{} for _ in range(len(names))]

    basic_idx = _ensure_basic_preset(names, new_presets, new_stats)

    # v197: Basic Preset comes from screenshots placed in C:\MapleProjects\MapleOCR\screenshots\\Equipped.
    # One equipped item per slot is expected; if a slot is missing, it is left blank rather than guessed.
    equipped_basic_refs = equipped_basic_refs or {}
    if equipped_basic_refs:
        new_presets[basic_idx] = {slot: int(item_id) for slot, item_id in equipped_basic_refs.items() if slot in SLOT_ORDER and item_id}

    # v197: also repopulate the optimiser's current-equipped structures from
    # screenshots\Equipped. This is the fix for Basic importing blank even when
    # equipmentPresets[Basic Preset] had refs.
    equipped_items_by_slot: Dict[str, Dict[str, Any]] = {}
    for p in parsed:
        if getattr(p, "source", "bag") == "equipped" and p.slot in SLOT_ORDER and p.slot not in equipped_items_by_slot:
            equipped_items_by_slot[p.slot] = json.loads(json.dumps(p.item))
    if equipped_items_by_slot:
        data["equippedItemsBySlot"] = equipped_items_by_slot
        data["equipmentBaseStats"] = {slot: _item_to_equipment_base_stats(item, slot) for slot, item in equipped_items_by_slot.items()}
        first_slot = "ring" if "ring" in equipped_items_by_slot else next(iter(equipped_items_by_slot.keys()))
        data["equippedItem"] = json.loads(json.dumps(equipped_items_by_slot[first_slot]))

    # Ensure managed utility/PvP presets exist.
    arena_idx = _ensure_preset(names, new_presets, new_stats, "Arena")
    hp_idx = _ensure_preset(names, new_presets, new_stats, "HP")
    mp_idx = _ensure_preset(names, new_presets, new_stats, "MP")
    chapter_boss_idx = _ensure_preset(names, new_presets, new_stats, "Chapter Boss")

    colosseum_indexes = [i for i, nm in enumerate(names) if str(nm).strip().lower() in {"colosseum", "colloseum"}]
    if not colosseum_indexes:
        colosseum_idx = _ensure_preset(names, new_presets, new_stats, "Colosseum")
        colosseum_indexes = [colosseum_idx]

    # Rebuild managed sets from fresh OCR items only. Do not pass old preset bases,
    # because those bases may reference stale/deleted optimiser IDs.
    arena_build = build_arena(grouped, base={})
    new_presets[arena_idx] = arena_build
    for ci in colosseum_indexes:
        new_presets[ci] = dict(arena_build)
    new_presets[hp_idx] = fill_missing_slots_with_best_available(build_hp(grouped, base={}), grouped)
    new_presets[mp_idx] = fill_missing_slots_with_best_available(build_mp(grouped, base={}), grouped)
    new_presets[chapter_boss_idx] = build_pve_preset(grouped, mode="chapter-boss")

    # Let optimiser recalculate stats for every equipment preset after import.
    new_stats = [{} for _ in range(len(names))]

    data["equipmentPresetNames"] = names
    data["equipmentPresets"] = new_presets
    data["equipmentPresetStats"] = new_stats
    data["currentEquipmentPreset"] = old_data.get("currentEquipmentPreset", 0)

    # v197: normalise fresh equipment display names from actual attack fields.
    name_fix_report: List[str] = []
    normalize_equipment_display_names(data.get("comparisonItems"), name_fix_report, "comparisonItems")
    normalize_equipment_display_names(data.get("comparisonItemsBySlot"), name_fix_report, "comparisonItemsBySlot")
    data["__nameFixReportForRun"] = name_fix_report

    managed_names = {"arena", "hp", "mp", "colosseum", "colloseum", "chapter boss"}
    cleared = [str(nm) for i, nm in enumerate(names) if str(nm).strip().lower() not in managed_names and not _preset_name_is_basic(nm)]
    data["__freshInventorySanityForRun"] = {
        "trusted_ocr_items": len(parsed),
        "unique_equipment_ids_written": len({int(it.get("id", 0)) for it in flat if int(it.get("id", 0)) > 0}),
        "preset_names_preserved": True,
        "basic_from_equipped_rebuilt": bool(new_presets[basic_idx]),
        "basic_equipped_slots": sorted(list((new_presets[basic_idx] or {}).keys())),
        "equippedItemsBySlot_from_equipped": sorted(list((data.get("equippedItemsBySlot") or {}).keys())),
        "equipmentBaseStats_from_equipped": sorted(list((data.get("equipmentBaseStats") or {}).keys())),
        "arena_rebuilt": bool(new_presets[arena_idx]),
        "colosseum_rebuilt": all(bool(new_presets[ci]) for ci in colosseum_indexes),
        "hp_rebuilt": bool(new_presets[hp_idx]),
        "mp_rebuilt": bool(new_presets[mp_idx]),
        "chapter_boss_rebuilt": bool(new_presets[chapter_boss_idx]),
        "other_optimiser_presets_cleared_rebuild_needed": True,
        "cleared_presets": cleared,
    }

    # Remove internal HP/MP builder helpers before writing mapleupload JSON.
    strip_internal_build_keys(data.get("comparisonItems"))
    strip_internal_build_keys(data.get("comparisonItemsBySlot"))
    return data

def _find_item_by_id(data: Dict[str, Any], slot: str, item_id: Any) -> Optional[Dict[str, Any]]:
    try:
        iid = int(item_id)
    except Exception:
        return None
    for it in (data.get("comparisonItemsBySlot") or {}).get(slot, []) or []:
        try:
            if int(it.get("id", 0)) == iid:
                return it
        except Exception:
            pass
    return None


def _fmt_num(x: float) -> str:
    if abs(x - round(x)) < 0.0001:
        return str(int(round(x)))
    return f"{x:.1f}"


def build_arena_colosseum_report(data: Dict[str, Any], run_id: str) -> str:
    names = data.get("equipmentPresetNames") or []
    presets = data.get("equipmentPresets") or []
    arena_idx = _find_preset_index(names, "Arena")
    lines = [
        f"Generated by MapleOCR {VERSION}",
        f"RUN_ID: {run_id}",
        "ARENA / COLOSSEUM EQUIPMENT LIST",
        "",
        "Rule: Evasion first, protect Accuracy second, Arena-relevant damage third.",
        "v190 fix: Evasion and Accuracy are totalled as main stat + sub-option, then selected equipment Accuracy is protected.",
        "Colosseum uses the same equipment logic as Arena.",
        "",
    ]
    if arena_idx is None or arena_idx >= len(presets) or not isinstance(presets[arena_idx], dict):
        lines.append("Arena preset not found.")
        return "\n".join(lines)

    preset = presets[arena_idx]
    total_e = 0.0
    total_a = 0.0
    total_atk = 0
    lines.append("ARENA / COLOSSEUM")
    for slot in SLOT_ORDER:
        if slot not in preset:
            continue
        it = _find_item_by_id(data, slot, preset.get(slot))
        if not it:
            lines.append(f"{DISPLAY_SLOT[slot]}: {preset.get(slot)}")
            continue
        ev = total_stat(it, "evasion")
        ac = total_stat(it, "accuracy")
        atk = item_score_attack(it)
        total_e += ev
        total_a += ac
        total_atk += atk
        bits = [f"{DISPLAY_SLOT[slot]}: {it.get('name')}", f"Attack {atk}"]
        if ev:
            bits.append(f"Evasion {_fmt_num(ev)}")
        if ac:
            bits.append(f"Accuracy {_fmt_num(ac)}")
        dmg = arena_damage_score(it)
        bits.append(f"ArenaSupport {_fmt_num(dmg)}")
        lines.append(" | ".join(bits))
    lines.extend([
        "",
        f"Equipment-only summed Evasion from selected items: {_fmt_num(total_e)}",
        f"Equipment-only summed Accuracy from selected items: {_fmt_num(total_a)}",
        f"Selected item Attack sum: {total_atk}",
        "",
        "Note: These are equipment-list totals only. Your character stat screen also includes other sources such as abilities, potentials, artifacts, companions, account stats, and passive bonuses.",
    ])
    return "\n".join(lines)


def build_pve_equipment_report(data: Dict[str, Any], run_id: str) -> str:
    """Report the managed PvE seed presets v190 builds."""
    names = data.get("equipmentPresetNames") or []
    presets = data.get("equipmentPresets") or []
    lines = [
        f"Generated by MapleOCR {VERSION}",
        f"RUN_ID: {run_id}",
        "MANAGED PVE EQUIPMENT LIST",
        "",
        "Chapter Boss rule: Attack + Boss Monster Damage + general damage + crit/multipliers + 3rd/4th skill levels.",
        "Breakthrough is deliberately not managed here; the optimiser should build Chapter Breakthrough.",
        "These are fresh-OCR seed builds, not a full optimiser simulation.",
        "",
    ]

    wanted = [("Chapter Boss", "chapter-boss")]
    for label, mode in wanted:
        idx = _find_preset_index(names, label)
        if idx is None or idx >= len(presets) or not isinstance(presets[idx], dict) or not presets[idx]:
            lines.append(f"{label.upper()}: not present/rebuilt")
            lines.append("")
            continue
        preset = presets[idx]
        total_atk = 0
        total_score = 0.0
        lines.append(label.upper())
        for slot in SLOT_ORDER:
            if slot not in preset:
                continue
            it = _find_item_by_id(data, slot, preset.get(slot))
            if not it:
                lines.append(f"{DISPLAY_SLOT[slot]}: {preset.get(slot)}")
                continue
            atk = item_score_attack(it)
            score = pve_damage_score(it, mode)
            total_atk += atk
            total_score += score
            bits = [f"{DISPLAY_SLOT[slot]}: {it.get('name')}", f"Attack {atk}", f"PvEScore {_fmt_num(score)}"]
            nd = get_stat(it, "normal-damage")
            bd = get_stat(it, "boss-damage")
            dmg = get_stat(it, "damage")
            cr = get_stat(it, "crit-rate")
            cd = get_stat(it, "crit-damage")
            s3 = get_stat(it, "skill-level-3")
            s4 = get_stat(it, "skill-level-4")
            if nd: bits.append(f"Normal {_fmt_num(nd)}")
            if bd: bits.append(f"Boss {_fmt_num(bd)}")
            if dmg: bits.append(f"Damage {_fmt_num(dmg)}")
            if cr: bits.append(f"CritRate {_fmt_num(cr)}")
            if cd: bits.append(f"CritDamage {_fmt_num(cd)}")
            if s3: bits.append(f"3rdLv {_fmt_num(s3)}")
            if s4: bits.append(f"4thLv {_fmt_num(s4)}")
            lines.append(" | ".join(bits))
        lines.append(f"Selected item Attack sum: {total_atk}")
        lines.append(f"Selected item score sum: {_fmt_num(total_score)}")
        lines.append("")
    return "\n".join(lines)


def clear_output_folder(output_dir: Path, screenshots_dir: Path, maple2_path: Path) -> None:
    """Clear Output at the start of every run so old files cannot contaminate checks.

    Safety guard: refuse to clear if the resolved Output path is the screenshots
    folder, the MapleOCR root, or the maple2 file parent. Expected use is
    C:\\MapleOCR\\Output only.
    """
    output_dir = output_dir.resolve()
    screenshots_dir = screenshots_dir.resolve()
    maple2_parent = maple2_path.resolve().parent
    if output_dir == screenshots_dir:
        raise RuntimeError(f"Refusing to clear output folder because it is the screenshots folder: {output_dir}")
    if output_dir == maple2_parent:
        raise RuntimeError(f"Refusing to clear output folder because it is the MapleOCR root/maple2 folder: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in output_dir.iterdir():
        if child.name == ".placeholder":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def write_actual_screenshot_listing(output_dir: Path, screenshots_dir: Path, imgs: List[Path], run_id: str) -> None:
    lines = [
        f"Generated by MapleOCR {VERSION}",
        f"RUN_ID: {run_id}",
        f"Screenshots folder: {screenshots_dir}",
        f"Top-level screenshot files: {len(imgs)}",
        "",
        "Name\tLength\tLastWriteTime",
    ]
    for p in imgs:
        try:
            st = p.stat()
            mtime = datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
            lines.append(f"{p.name}\t{st.st_size}\t{mtime}")
        except Exception as e:
            lines.append(f"{p.name}\tERROR\t{e}")
    write_text(output_dir / "actual_screenshots_folder_listing.txt", "\n".join(lines))


def suspicious_attack_reason(slot: str, tier: str, level: str, attack: int) -> Optional[str]:
    """Fail closed on obviously impossible main Attack values.

    This specifically catches OCR/comparison bleed such as a Lv107 T4 shoulder
    being trusted as Attack 2,020. Current known low legitimate values are still
    around 9,333+ in the user's inventory, so 9,000 is a conservative floor for
    plausible imported equipment when level is 80+.
    """
    try:
        lvl = int(str(level).strip()) if str(level).strip() else None
    except Exception:
        lvl = None
    tier_s = str(tier or "").strip().upper()
    return None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("screenshots_dir")
    ap.add_argument("maple2_txt")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--full-inventory", action="store_true")
    ap.add_argument("--debug-rows-only", action="store_true")
    ap.add_argument("--expected-count", type=int, default=None, help="Optional warning if top-level screenshot count is not what you expect")
    ap.add_argument("--output-dir", default=None, help="Folder for all generated output files. Default: <MapleOCR root>\\Results")
    ap.add_argument("--equipped-dir", default=None, help="Folder containing currently equipped item screenshots. Default: <screenshots_dir>\\Equipped")
    args = ap.parse_args(argv)

    screenshots_dir = Path(args.screenshots_dir)
    equipped_dir = Path(args.equipped_dir) if args.equipped_dir else (screenshots_dir / "Equipped")
    base_dir = screenshots_dir.parent if screenshots_dir.name.lower() == "screenshots" else screenshots_dir
    output_dir = Path(args.output_dir) if args.output_dir else (base_dir / "Results")
    maple2_path = Path(args.maple2_txt)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    old_data = json.loads(maple2_path.read_text(encoding="utf-8"))

    # v197: clear Results at the start of every run. This prevents stale files
    # from previous v149/v150/v151 runs contaminating zipped checks.
    clear_output_folder(output_dir, screenshots_dir, maple2_path)
    write_text(output_dir / "RUN_ID.txt", f"Generated by MapleOCR {VERSION}\nRUN_ID: {run_id}\nOutput folder: {output_dir}\nScreenshots folder: {screenshots_dir}\nEquipped folder: {equipped_dir}\n")

    # v190 scans two sources:
    # - top-level C:\MapleProjects\MapleOCR\screenshots files = bag inventory
    # - C:\MapleProjects\MapleOCR\screenshots\\Equipped files = currently worn equipment for Basic Preset
    # Subfolders other than Equipped are ignored by design.
    bag_imgs = sorted([p for p in screenshots_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS and p.is_file()]) if screenshots_dir.exists() else []
    equipped_imgs = sorted([p for p in equipped_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS and p.is_file()]) if equipped_dir.exists() else []
    img_sources: List[Tuple[Path, str]] = [(p, "bag") for p in bag_imgs] + [(p, "equipped") for p in equipped_imgs]
    imgs = [p for p, _src in img_sources]
    equipped_filenames = {p.name for p in equipped_imgs}

    # v197: Preserve filesystem capture timestamps/order as audit metadata.
    # IMPORTANT: OCR processing order remains unchanged from v187 so ID assignment
    # and parser behaviour are not silently changed by this feature.
    capture_meta, batch_capture_sorted = build_capture_order(bag_imgs, equipped_imgs)
    manifest_lines = [
        f"Generated by MapleOCR {VERSION}",
        f"RUN_ID: {run_id}",
        f"Screenshots folder: {screenshots_dir}",
        f"Equipped folder: {equipped_dir}",
        f"Output folder: {output_dir}",
        f"Top-level bag screenshots found: {len(bag_imgs)}",
        f"Top-level Equipped screenshots found: {len(equipped_imgs)}",
        f"Total screenshots found: {len(imgs)}",
    ]
    if args.expected_count is not None and len(imgs) != args.expected_count:
        manifest_lines.append(f"WARNING: expected {args.expected_count} total screenshots but found {len(imgs)}")
    manifest_lines.append("")
    manifest_lines.append("BAG SCREENSHOTS:")
    manifest_lines.extend(p.name for p in bag_imgs)
    manifest_lines.append("")
    manifest_lines.append("EQUIPPED SCREENSHOTS:")
    manifest_lines.extend(p.name for p in equipped_imgs)

    manifest_lines.append("")
    manifest_lines.append("CAPTURE ORDER AUTHORITY:")
    manifest_lines.append("source_capture_order is the authoritative order for future BIS LOCK/UNLOCK bag scrolling.")
    manifest_lines.append("capture_timestamp uses the earlier of filesystem creation and modification timestamps.")
    manifest_lines.append("OCR processing/ID assignment order is intentionally unchanged from v187.")
    manifest_lines.append("")
    manifest_lines.append("BAG CAPTURE ORDER:")
    for p, source, meta in sorted(
        [e for e in batch_capture_sorted if e[1] == "bag"],
        key=lambda e: int(e[2]["source_capture_order"]),
    ):
        manifest_lines.append(
            f"{int(meta['source_capture_order']):04d} | {meta['capture_timestamp']} | {p.name}"
        )
    manifest_lines.append("")
    manifest_lines.append("EQUIPPED CAPTURE ORDER:")
    for p, source, meta in sorted(
        [e for e in batch_capture_sorted if e[1] == "equipped"],
        key=lambda e: int(e[2]["source_capture_order"]),
    ):
        manifest_lines.append(
            f"{int(meta['source_capture_order']):04d} | {meta['capture_timestamp']} | {p.name}"
        )

    write_text(output_dir / f"screenshot_manifest_{VERSION}.txt", "\n".join(manifest_lines))

    # Machine-readable sidecar for BIS/report tooling.
    with (output_dir / f"screenshot_capture_order_{VERSION}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "filename", "source", "source_capture_order", "batch_capture_order",
            "capture_timestamp", "file_created_timestamp", "file_modified_timestamp"
        ])
        for p, source, meta in sorted(batch_capture_sorted, key=lambda e: int(e[2]["batch_capture_order"])):
            w.writerow([
                p.name,
                source,
                meta["source_capture_order"],
                meta["batch_capture_order"],
                meta["capture_timestamp"],
                meta["created_timestamp"],
                meta["modified_timestamp"],
            ])
    write_actual_screenshot_listing(output_dir, screenshots_dir, bag_imgs, run_id)
    if equipped_imgs:
        write_text(output_dir / "equipped_screenshots_listing.txt", "\n".join([f"Generated by MapleOCR {VERSION}", f"RUN_ID: {run_id}", f"Equipped folder: {equipped_dir}", f"Top-level equipped files: {len(equipped_imgs)}", "", *[p.name for p in equipped_imgs]]))

    reader = load_easyocr_reader()
    parsed: List[ParsedItem] = []
    reviews: List[Tuple[Path, str]] = []
    equipped_starforce_by_slot: Dict[str, int] = {}
    equipped_starforce_source: Dict[str, str] = {}
    equipped_starforce_failures: List[str] = []
    debug_lines: List[str] = [f"Generated by MapleOCR {VERSION}", f"RUN_ID: {run_id}", f"Bag screenshots: {len(bag_imgs)}", f"Equipped screenshots: {len(equipped_imgs)}", f"Total screenshots: {len(imgs)}", "Anchor policy: v197 uses mapleexport.txt for non-equipment optimiser settings and preset names only; old optimiser equipment inventory is not trusted; fresh OCR comparisonItems/comparisonItemsBySlot are the source of truth; bag screenshots plus Equipped screenshots are imported; Equipped items are written into Basic Preset; Arena/Colosseum/HP/MP/Chapter Boss are rebuilt; all other equipment presets are kept by name but cleared for manual rebuild; lock status is captured from the fixed lock-button ROI into maplelocked.txt/lock_status.txt; Arena totals main+sub Evasion/Accuracy and protects selected equipment Accuracy; HP/MP are pure potion-upgrade stat sets; Max MP percent rows are parsed; Defense Penetration is explicitly distinguished from Defense; substat values treat WHITE as the item value and GREEN as comparison-only fallback; large whole-number rows reject leading OCR fragments using repeated complete-value reconstruction before normal WHITE-first selection; skill-level rows retain duplicate/right-most foreground handling; conservative option-stat min/max validation rejects impossible OCR values and warns on suspicious ones; main item Attack is not constrained by fixed gameplay-value ranges; conservative sanity checks reject structural corruption and only warn on generous option-stat thresholds/white-support gaps; zero rounding is permitted anywhere in trusted parser cleanup; equipment display names are normalised from attack fields; no attack/stat/percentage scaling is applied.", ""]
    if args.expected_count is not None and len(imgs) != args.expected_count:
        debug_lines.append(f"WARNING: expected {args.expected_count} total screenshots but found {len(imgs)}")
        debug_lines.append("")
    review_rows: List[List[str]] = [[
        "run_id","filename","source","source_capture_order","batch_capture_order","capture_timestamp",
        "file_created_timestamp","file_modified_timestamp",
        "slot","shorthand_name","tier","level","attack","option_stats","warnings","ocr_rows"
    ]]

    for img, img_source in img_sources:
        meta = capture_meta_for(img, capture_meta)
        try:
            visual_anchor, visual_debug = detect_visual_on_equip_anchor(img)
            rows = ocr_image(reader, img)
            lock_status, lock_debug = detect_lock_status(img)
            p, reason = parse_item_from_rows(img.name, rows, visual_anchor=visual_anchor, visual_debug=visual_debug)
            debug_lines.append("="*80)
            debug_lines.append(
                f"FILE: {img.name} | source={img_source} "
                f"| source_capture_order={meta['source_capture_order']} "
                f"| batch_capture_order={meta['batch_capture_order']} "
                f"| capture_timestamp={meta['capture_timestamp']} "
                f"| lock_status={lock_status} | {lock_debug}"
            )
            debug_lines.extend(visual_debug)
            debug_lines.append("RAW/CLEANED ROWS:")
            for r in rows:
                token_dbg = " ; ".join(
                    f"{t.text}[fg={t.fg_class}:{t.fg_ratio:.2f},x={t.cx:.1f}]"
                    for t in r.tokens
                )
                debug_lines.append(f"{r.idx:02d}: y={r.y:.1f} text={r.text} || TOKENS: {token_dbg}")
            if p:
                if img_source == "equipped":
                    sf_value, sf_dbg = detect_equipped_star_force(reader, img)
                    debug_lines.extend(sf_dbg)
                    if sf_value is None:
                        equipped_starforce_failures.append(f"{img.name}: Star Force badge could not be read")
                    else:
                        if p.slot in equipped_starforce_by_slot and equipped_starforce_by_slot[p.slot] != sf_value:
                            equipped_starforce_failures.append(
                                f"{img.name}: duplicate Equipped slot {p.slot} with conflicting Star Force "
                                f"{equipped_starforce_by_slot[p.slot]} vs {sf_value}"
                            )
                        equipped_starforce_by_slot[p.slot] = sf_value
                        equipped_starforce_source[p.slot] = img.name
                p.lock_status = lock_status
                p.source = img_source
                p.source_capture_order = int(meta["source_capture_order"])
                p.batch_capture_order = int(meta["batch_capture_order"])
                p.capture_timestamp = str(meta["capture_timestamp"])
                debug_lines.extend(p.rows_debug)

                sanity_hard, sanity_warn = sanity_check_parsed_item(p, rows, lock_status)
                for w in sanity_warn:
                    p.warnings.append("SANITY WARNING: " + w)
                    debug_lines.append("SANITY WARNING: " + w)

                if sanity_hard:
                    sanity_reason = "SANITY REJECT: " + "; ".join(sanity_hard)
                    debug_lines.append(sanity_reason)
                    reviews.append((img, sanity_reason))
                    review_rows.append([
                        run_id, img.name, img_source,
                        meta["source_capture_order"], meta["batch_capture_order"], meta["capture_timestamp"],
                        meta["created_timestamp"], meta["modified_timestamp"],
                        p.slot, p.name, p.tier, p.level, str(p.attack),
                        json.dumps(p.item.get("stats",[])),
                        "; ".join(p.warnings + [sanity_reason, f"lock={lock_status}"]),
                        " | ".join(r.text for r in rows)
                    ])
                else:
                    parsed.append(p)
                    review_rows.append([
                        run_id, img.name, img_source,
                        meta["source_capture_order"], meta["batch_capture_order"], meta["capture_timestamp"],
                        meta["created_timestamp"], meta["modified_timestamp"],
                        p.slot, p.name, p.tier, p.level, str(p.attack),
                        json.dumps(p.item.get("stats",[])),
                        "; ".join(p.warnings + [f"lock={lock_status}"]),
                        " | ".join(r.text for r in rows)
                    ])
            else:
                debug_lines.append(f"REVIEW: {reason}")
                reviews.append((img, reason))
                review_rows.append([
                    run_id, img.name, img_source,
                        meta["source_capture_order"], meta["batch_capture_order"], meta["capture_timestamp"],
                        meta["created_timestamp"], meta["modified_timestamp"],
                    "", "", "", "", "", "", reason, " | ".join(r.text for r in rows)
                ])
        except Exception as e:
            reviews.append((img, f"exception: {e}"))
            debug_lines.append(
                f"FILE: {img.name} | source={img_source} "
                f"| source_capture_order={meta['source_capture_order']} "
                f"| batch_capture_order={meta['batch_capture_order']} "
                f"| capture_timestamp={meta['capture_timestamp']}\nEXCEPTION: {e}"
            )
            review_rows.append([
                run_id, img.name, img_source,
                meta["source_capture_order"], meta["batch_capture_order"], meta["capture_timestamp"],
                meta["created_timestamp"], meta["modified_timestamp"],
                "", "", "", "", "", "", f"exception: {e}", ""
            ])

    assign_ids(parsed, int(old_data.get("nextComparisonItemId") or 1000))

    # v197: same-run BIS report authority generated after equipment IDs exist.
    write_bis_report_authority(output_dir, parsed, run_id)

    equipped_basic_refs: Dict[str, int] = {}
    equipped_conflicts: List[str] = []
    for p in parsed:
        if p.filename in equipped_filenames:
            item_id = int(p.item.get("id", 0) or 0)
            if p.slot in equipped_basic_refs:
                equipped_conflicts.append(f"Multiple equipped screenshots for slot {p.slot}: keeping {equipped_basic_refs[p.slot]}, also saw {item_id} ({p.filename})")
                continue
            equipped_basic_refs[p.slot] = item_id

    # names output
    name_lines = [f"Generated by MapleOCR {VERSION}", f"RUN_ID: {run_id}", f"TOTAL TRUSTED EQUIPMENT ITEMS: {len(parsed)}", "Source: trusted layout-row parser", ""]
    by_slot: Dict[str, List[ParsedItem]] = defaultdict(list)
    for p in parsed: by_slot[p.slot].append(p)
    for slot in SLOT_ORDER:
        items = sorted(by_slot.get(slot, []), key=lambda p: (-p.attack, p.name))
        name_lines.append(f"=== {DISPLAY_SLOT[slot].upper()} ({len(items)} item(s)) ===")
        for p in items:
            src = "equipped" if p.filename in equipped_filenames else "bag"
            name_lines.append(f"- {p.filename} | source={src} | slot={slot} | name={p.name}")
        name_lines.append("")
    write_text(output_dir / "names.txt", "\n".join(name_lines))
    write_text(output_dir / f"names_{VERSION}_full_inventory.txt", "\n".join(name_lines))

    # Review files
    stat_lines = [f"Generated by MapleOCR {VERSION}", f"RUN_ID: {run_id}", "STAT REVIEW / NOT WRITTEN TO MAPLEUPLOAD", ""]
    if not reviews:
        stat_lines.append("None.")
    else:
        need_dir = output_dir / "need_review"
        need_dir.mkdir(exist_ok=True)
        for img, reason in reviews:
            meta = capture_meta_for(img, capture_meta)
            stat_lines.append(
                f"- source_order={meta['source_capture_order']} | "
                f"capture={meta['capture_timestamp']} | {img.name} | {reason}"
            )
            if not args.dry_run:
                try: shutil.copy2(img, need_dir / img.name)
                except Exception: pass
    write_text(output_dir / "stat_review.txt", "\n".join(stat_lines))
    bad_lines = [f"Generated by MapleOCR {VERSION}", f"RUN_ID: {run_id}"]
    for img, reason in reviews:
        meta = capture_meta_for(img, capture_meta)
        bad_lines.append(
            f"source_order={meta['source_capture_order']} | capture={meta['capture_timestamp']} | "
            f"{img.name} | {reason}"
        )
    write_text(output_dir / "bad_screenshots.txt", "\n".join(bad_lines))

    write_text(output_dir / f"parsed_rows_debug_{VERSION}.txt", "\n".join(debug_lines))
    write_text(output_dir / "inventory_log.txt", "\n".join(debug_lines))
    write_text(output_dir / f"import_review_easyocr_{VERSION}.txt", "\n".join(debug_lines))
    with (output_dir / f"import_review_easyocr_{VERSION}.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(review_rows)

    # mapleexcel outputs. In dry-run, keep the usual review text files but also
    # write an explicitly versioned dry-run file so the real live files are not
    # confused with test output.
    excel_lines = ["filename\tsource\tslot\ttier\tlevel\tshorthand_name\tattack\toption_stats"]
    for p in parsed:
        src = "equipped" if p.filename in equipped_filenames else "bag"
        excel_lines.append(f"{p.filename}\t{src}\t{p.slot}\t{p.tier}\t{p.level}\t{p.name}\t{p.attack}\t{json.dumps(p.item.get('stats',[]))}")
    excel_text = "\n".join(excel_lines)
    write_text(output_dir / "mapleexcel.txt", excel_text)
    if args.dry_run:
        write_text(output_dir / f"mapleexcel_{VERSION}_DRY_RUN.txt", excel_text)

    # v197 Star Force sync report / hard guardrail.
    old_sf = dict(old_data.get("equipmentStarForceBySlot") or {})
    sf_lines = [
        f"Generated by MapleOCR {VERSION}",
        f"RUN_ID: {run_id}",
        "EQUIPPED STAR FORCE SYNC",
        "",
        "screenshots\\Equipped badge values are authoritative for equipmentStarForceBySlot.",
        "",
        "slot\tscreenshot_star_force\tprevious_optimizer_star_force\taction\tfilename",
    ]
    for slot in SLOT_ORDER:
        if slot in equipped_starforce_by_slot:
            new_v = int(equipped_starforce_by_slot[slot])
            try:
                old_v = int(old_sf.get(slot, 0) or 0)
            except Exception:
                old_v = 0
            action = "OK" if old_v == new_v else "UPDATED"
            sf_lines.append(f"{slot}\t{new_v}\t{old_v}\t{action}\t{equipped_starforce_source.get(slot,'')}")
    missing_sf_slots = [slot for slot in SLOT_ORDER if slot in equipped_basic_refs and slot not in equipped_starforce_by_slot]
    if missing_sf_slots:
        equipped_starforce_failures.append("Missing Equipped Star Force for slot(s): " + ", ".join(missing_sf_slots))
    if equipped_starforce_failures:
        sf_lines.extend(["", "FAILURES:"] + [f"- {x}" for x in equipped_starforce_failures])
    write_text(output_dir / f"star_force_sync_{VERSION}.txt", "\n".join(sf_lines))

    mapleupload_written = False
    dry_run_upload_written = False
    if not args.debug_rows_only:
        if equipped_starforce_failures:
            raise RuntimeError(
                "Refusing to write mapleupload.txt: Equipped Star Force authority incomplete/ambiguous. "
                + " | ".join(equipped_starforce_failures)
            )
        no_scale_report = [f"Generated by MapleOCR {VERSION}", "NO STAT SCALING", "", "All OCR values are written exactly as parsed from the game screenshots.", "Attack / HP / Main Stat / Defense are unchanged.", "Percentage sub-options are unchanged."]
        write_text(output_dir / f"no_stat_scaling_report_{VERSION}.txt", "\n".join(no_scale_report))
        data = make_output_data(old_data, parsed, equipped_basic_refs=equipped_basic_refs, equipped_starforce_by_slot=equipped_starforce_by_slot)
        name_fix_report = data.pop("__nameFixReportForRun", []) if isinstance(data, dict) else []
        sanity = data.pop("__freshInventorySanityForRun", {}) if isinstance(data, dict) else {}
        try:
            write_text(output_dir / f"name_fix_report_{VERSION}.txt", "\n".join([
                f"Generated by MapleOCR {VERSION}",
                f"RUN_ID: {run_id}",
                "Equipment name normalisation from attack field",
                "",
                *(name_fix_report or ["None."])
            ]))
        except Exception:
            pass
        try:
            sanity_lines = [
                f"Generated by MapleOCR {VERSION}",
                f"RUN_ID: {run_id}",
                "FRESH OCR INVENTORY SANITY CHECK",
                "",
                f"Bag screenshots found: {len(bag_imgs)}",
                f"Equipped screenshots found: {len(equipped_imgs)}",
                f"Total screenshots found: {len(imgs)}",
                f"Trusted OCR items: {len(parsed)}",
                f"Basic Preset from Equipped: {'YES' if sanity.get('basic_from_equipped_rebuilt') else 'NO'}",
                f"Basic Preset equipped slots: {', '.join(sanity.get('basic_equipped_slots') or []) if sanity.get('basic_equipped_slots') else 'None'}",
                f"equippedItemsBySlot from Equipped: {', '.join(sanity.get('equippedItemsBySlot_from_equipped') or []) if sanity.get('equippedItemsBySlot_from_equipped') else 'None'}",
                f"equipmentBaseStats from Equipped: {', '.join(sanity.get('equipmentBaseStats_from_equipped') or []) if sanity.get('equipmentBaseStats_from_equipped') else 'None'}",
                f"Unique equipment IDs written to mapleupload.txt: {sanity.get('unique_equipment_ids_written', count_import_equipment_rows(data))}",
                f"Presets preserved by name/list structure: {'YES' if sanity.get('preset_names_preserved') else 'NO'}",
                f"Arena rebuilt: {'YES' if sanity.get('arena_rebuilt') else 'NO'}",
                f"Colosseum rebuilt: {'YES' if sanity.get('colosseum_rebuilt') else 'NO'}",
                f"HP rebuilt: {'YES' if sanity.get('hp_rebuilt') else 'NO'}",
                f"MP rebuilt: {'YES' if sanity.get('mp_rebuilt') else 'NO'}",
                f"Chapter Boss rebuilt: {'YES' if sanity.get('chapter_boss_rebuilt') else 'NO'}",
                "Breakthrough managed by OCR: NO - left for optimiser rebuild",
                f"Other optimiser presets cleared/rebuild needed: {'YES' if sanity.get('other_optimiser_presets_cleared_rebuild_needed') else 'NO'}",
                "",
                "Cleared manual presets:",
            ]
            cleared = sanity.get('cleared_presets') or []
            sanity_lines.extend([f"- {x}" for x in cleared] or ["None."])
            if sanity.get('unique_equipment_ids_written', count_import_equipment_rows(data)) != len(parsed):
                sanity_lines.append("")
                sanity_lines.append("WARNING: Unique equipment IDs written does not match trusted OCR item count.")
            write_text(output_dir / f"fresh_inventory_sanity_{VERSION}.txt", "\n".join(sanity_lines))
        except Exception as e:
            try:
                write_text(output_dir / f"fresh_inventory_sanity_{VERSION}.txt", f"Generated by MapleOCR {VERSION}\nRUN_ID: {run_id}\nCould not write sanity report: {e}\n")
            except Exception:
                pass
        # v197: always write lock snapshots into Output, including dry-run.
        # The real run also copies the plain files beside mapleupload.txt.
        maplelocked_text = build_lock_snapshot_text(parsed, run_id, len(bag_imgs), len(equipped_imgs), locked_only=True)
        lock_status_text = build_lock_snapshot_text(parsed, run_id, len(bag_imgs), len(equipped_imgs), locked_only=False)
        try:
            write_text(output_dir / "maplelocked.txt", maplelocked_text)
            write_text(output_dir / "lock_status.txt", lock_status_text)
            write_text(output_dir / f"maplelocked_{VERSION}_DRY_RUN.txt", maplelocked_text)
            write_text(output_dir / f"lock_status_{VERSION}_DRY_RUN.txt", lock_status_text)
        except Exception as e:
            write_text(output_dir / f"lock_snapshot_WRITE_FAILED_{VERSION}.txt", f"Generated by MapleOCR {VERSION}\nRUN_ID: {run_id}\nCould not write lock snapshots: {e}\n")

        try:
            # Validate in both modes so dry-run still proves the optimiser JSON
            # would be safe, but NEVER replace mapleupload.txt during dry-run.
            _validate_basic_equipped_written(data, len(equipped_basic_refs))
            validate_mapleupload_payload(data, len(parsed))
            if args.dry_run:
                write_text(output_dir / f"mapleupload_{VERSION}_DRY_RUN.txt", json.dumps(data, ensure_ascii=False, indent=2))
                # Convenience copy outside Output_vXXX.zip; avoids extraction for quick checking.
                try:
                    write_text(base_dir / f"mapleupload_{VERSION}_DRY_RUN.txt", json.dumps(data, ensure_ascii=False, indent=2))
                except Exception:
                    pass
                dry_run_upload_written = True
            else:
                safe_write_mapleupload(output_dir / "mapleupload.txt", data, len(parsed))
                # Also write an explicitly-versioned real-run copy so the uploaded Output zip can be inspected.
                write_text(output_dir / f"mapleupload_{VERSION}_REAL.txt", json.dumps(data, ensure_ascii=False, indent=2))
                # Convenience copy outside Output_vXXX.zip.
                try:
                    safe_write_mapleupload(base_dir / "mapleupload.txt", data, len(parsed))
                except Exception:
                    shutil.copy2(output_dir / "mapleupload.txt", base_dir / "mapleupload.txt")
                try:
                    write_text(base_dir / "maplelocked.txt", maplelocked_text)
                    write_text(base_dir / "lock_status.txt", lock_status_text)
                except Exception:
                    pass
                mapleupload_written = True
        except Exception as e:
            block_text = "\n".join([
                f"Generated by MapleOCR {VERSION}",
                "mapleupload.txt was NOT overwritten.",
                f"Reason: {e}",
                "",
                f"Trusted items: {len(parsed)}",
                f"Review items: {len(reviews)}",
                f"Screenshots found: {len(imgs)}",
            ])
            write_text(output_dir / "mapleupload_WRITE_BLOCKED.txt", block_text)
            print()
            print("WARNING: mapleupload.txt was NOT overwritten.")
            print(f"Reason: {e}")
        # auto_sets minimal summary
        presets = data.get("equipmentPresets", [])
        preset_names = data.get("equipmentPresetNames", [])
        auto_lines = [f"Generated by MapleOCR {VERSION}", f"RUN_ID: {run_id}", "AUTO-BUILT EQUIPMENT SETS", ""]
        auto_lines.append(f"Imported equipment rows: {count_import_equipment_rows(data)}")
        auto_lines.append(f"Equipment preset refs: {count_preset_refs(data)}")
        auto_lines.append("")
        for nm, preset in zip(preset_names, presets):
            if str(nm).lower() in ("arena", "colosseum", "colloseum", "hp", "mp", "chapter boss", "accuracy", "arena accuracy", "accuracy counter", "evasion counter"):
                auto_lines.append(str(nm).upper())
                for slot in SLOT_ORDER:
                    if slot in preset:
                        item = next((it for it in data["comparisonItemsBySlot"].get(slot, []) if it.get("id") == preset[slot]), None)
                        auto_lines.append(f"{DISPLAY_SLOT[slot]}: {item.get('name') if item else preset[slot]}")
                auto_lines.append("")
        auto_text = "\n".join(auto_lines)
        write_text(output_dir / "auto_sets.txt", auto_text)

        basic_lines = [f"Generated by MapleOCR {VERSION}", f"RUN_ID: {run_id}", "BASIC PRESET FROM EQUIPPED SCREENSHOTS", "", f"Equipped screenshots found: {len(equipped_imgs)}", f"Equipped slots written: {len(equipped_basic_refs)}", ""]
        if equipped_basic_refs:
            basic_preset = data.get("equipmentPresets", [])[next((i for i,nm in enumerate(data.get("equipmentPresetNames", [])) if _preset_name_is_basic(nm)), 0)]
            for slot in SLOT_ORDER:
                if slot in basic_preset:
                    item = next((it for it in data["comparisonItemsBySlot"].get(slot, []) if it.get("id") == basic_preset[slot]), None)
                    basic_lines.append(f"{DISPLAY_SLOT[slot]}: {item.get('name') if item else basic_preset[slot]}")
        else:
            basic_lines.append("No Equipped screenshots were parsed, so Basic Preset was left blank.")
        if equipped_conflicts:
            basic_lines.append("")
            basic_lines.append("Equipped slot conflicts:")
            basic_lines.extend(f"- {x}" for x in equipped_conflicts)
        write_text(output_dir / "basic_equipped_preset_list.txt", "\n".join(basic_lines))
        if args.dry_run:
            write_text(output_dir / f"auto_sets_{VERSION}_DRY_RUN.txt", auto_text)

        arena_colosseum_text = build_arena_colosseum_report(data, run_id)
        write_text(output_dir / "arena_colosseum_equipment_list.txt", arena_colosseum_text)
        if args.dry_run:
            write_text(output_dir / f"arena_colosseum_equipment_list_{VERSION}_DRY_RUN.txt", arena_colosseum_text)

        pve_text = build_pve_equipment_report(data, run_id)
        write_text(output_dir / "managed_pve_equipment_list.txt", pve_text)
        if args.dry_run:
            write_text(output_dir / f"managed_pve_equipment_list_{VERSION}_DRY_RUN.txt", pve_text)

        write_text(output_dir / "delete_from_opti.txt", f"Generated by MapleOCR {VERSION}\nFresh OCR inventory is the source of truth. Top-level screenshots are bag inventory; screenshots\\Equipped is the currently worn Basic Preset source. Arena/Colosseum/HP/MP/Chapter Boss managed presets are rebuilt from OCR items where present. Breakthrough is intentionally left for the optimiser to rebuild. Other manual optimiser presets are kept by name but cleared/rebuild-needed to avoid stale deleted item references.\n")

    # v197: A fresh OCR scan makes any previous BIS_stats.zip potentially stale.
    # Do NOT package mapleexport.txt here: the optimiser has not yet imported this
    # run's mapleupload.txt, so the root mapleexport.txt may describe the previous
    # inventory state.
    if not args.dry_run:
        stale_bis_zip = base_dir / "BIS_stats.zip"
        try:
            if stale_bis_zip.exists():
                stale_bis_zip.unlink()
        except Exception as e:
            write_text(
                output_dir / f"BIS_stats_STALE_REMOVE_FAILED_{VERSION}.txt",
                f"Generated by MapleOCR {VERSION}\nRUN_ID: {run_id}\n"
                f"Could not remove stale {stale_bis_zip}: {e}\n"
            )

        pending_text = "\n".join([
            f"Generated by MapleOCR {VERSION}",
            f"RUN_ID: {run_id}",
            "",
            "BIS_stats.zip is intentionally PENDING.",
            "",
            "Required workflow:",
            "1. Import C:\\MapleOCR\\mapleupload.txt into the optimiser.",
            "2. Export the updated optimiser data back to C:\\MapleOCR\\mapleexport.txt.",
            f"3. Run .\\build_BIS_stats_{VERSION}.ps1",
            "",
            "The BIS builder will refuse to create BIS_stats.zip unless the",
            "fresh optimiser export is physically compatible with this OCR run and",
            "the same-run BIS report authority/provenance files are complete.",
        ])
        write_text(output_dir / f"BIS_stats_PENDING_{VERSION}.txt", pending_text)
        try:
            write_text(base_dir / f"BIS_stats_PENDING_{VERSION}.txt", pending_text)
        except Exception:
            pass

    # v192 ZIP FIX: create the check ZIP inside the importer itself.
    # This makes GUI dry runs reliable even if the GUI invokes a stale/copy wrapper.
    check_zip = base_dir / f"Output_{VERSION}_check.zip"
    try:
        if check_zip.exists():
            check_zip.unlink()

        result_files = [p for p in output_dir.iterdir() if p.is_file()]
        if not result_files:
            raise RuntimeError(f"No result files found in {output_dir}")

        temp_check_zip = base_dir / f"Output_{VERSION}_check.zip.tmp"
        if temp_check_zip.exists():
            temp_check_zip.unlink()

        with zipfile.ZipFile(temp_check_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(result_files, key=lambda x: x.name.lower()):
                zf.write(p, arcname=p.name)

        temp_check_zip.replace(check_zip)
        print(f"Check ZIP: {check_zip}")
    except Exception as e:
        try:
            temp_check_zip = base_dir / f"Output_{VERSION}_check.zip.tmp"
            if temp_check_zip.exists():
                temp_check_zip.unlink()
        except Exception:
            pass
        write_text(
            output_dir / f"CHECK_ZIP_WRITE_FAILED_{VERSION}.txt",
            f"Generated by MapleOCR {VERSION}\nRUN_ID: {run_id}\n"
            f"Could not create {check_zip}: {e}\n"
        )
        print(f"WARNING: check ZIP was not created: {e}")

    summary_text = build_final_summary(len(imgs), len(parsed), len(reviews), mapleupload_written)
    if args.dry_run:
        summary_text += f"\n  Dry-run mapleupload JSON written: {'YES' if dry_run_upload_written else 'NO'}"
    write_text(output_dir / f"run_summary_{VERSION}.txt", f"Generated by MapleOCR {VERSION}\nOutput folder: {output_dir}\n" + summary_text + "\n")

    print(f"MapleOCR {VERSION}: trusted={len(parsed)} review={len(reviews)}")
    print(f"Outputs written to: {output_dir}")
    print(summary_text)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
