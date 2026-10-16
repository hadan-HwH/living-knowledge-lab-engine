"""Track-E-lite extractor — we-volley planning/DECISIONS.md -> candidate event ledger.

Semi-structured input: `## NNNN · title (YYYY-MM-DD) → **MMMM로 대체**`.
Reliable: decision id, date, title, TITLE-level full-supersede markers.
NOT reliable (flagged for owner adjudication): partial markers ("③은 MMMM으로 대체")
and body-only supersede/refine relations. This gap is the extraction-fidelity finding.

Output is a *proposal* (§10): the owner adjudicates flagged items separately.

Usage: python3 ingest_wevolley.py [path/to/DECISIONS.md] > fixtures/wevolley-full/events.auto.yaml
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
import yaml

DEFAULT_MD = Path.home() / "Documents/we-volley/planning/DECISIONS.md"

HEADER = re.compile(r"^## (\d{4}) · (.+)$")
DATE = re.compile(r"\((\d{4}-\d{2}-\d{2})")
SUPERSEDE = re.compile(r"→ \*\*(.+?)\*\*")
TARGET_NUM = re.compile(r"(\d{4})")
PARTIAL = re.compile(r"[①②③④⑤⑥]")


def parse(md_path):
    entries = []
    for line in Path(md_path).read_text(encoding="utf-8").splitlines():
        m = HEADER.match(line)
        if not m:
            continue
        num, rest = m.group(1), m.group(2)
        date_m = DATE.search(rest)
        sup = SUPERSEDE.search(rest)
        superseded_by, partial = None, False
        if sup:
            marker = sup.group(1)
            tnum = TARGET_NUM.search(marker)
            superseded_by = tnum.group(1) if tnum else None
            partial = bool(PARTIAL.search(marker))
        title = SUPERSEDE.split(DATE.split(rest)[0])[0].strip().rstrip("(").strip()
        entries.append({
            "id": num, "title": title,
            "date": date_m.group(1) if date_m else None,
            "superseded_by": superseded_by, "partial": partial,
        })
    return entries


def build(entries):
    by_id = {e["id"]: e for e in entries}
    # full (non-partial) title supersede links: A superseded_by B  =>  supersedes_map[B] = A
    supersedes_map = {e["superseded_by"]: e["id"]
                      for e in entries if e["superseded_by"] and not e["partial"]}

    def _base(idx):                       # follow chain down to the original option
        seen = set()
        while idx in supersedes_map and idx not in seen:
            seen.add(idx)
            idx = supersedes_map[idx]
        return idx

    events, flagged, emitted = [], [], set()

    def adopt(idx, target):
        events.append({"event_id": f"WV.act.{idx}", "type": "adopt", "target": target,
                       "option": f"o{idx}", "authority_level": "product", "scope": "wevolley",
                       "valid_at": by_id[idx]["date"], "recorded_at": by_id[idx]["date"],
                       "title": by_id[idx]["title"]})
        emitted.add(idx)

    # pass 1: full supersede chains
    for b, a in supersedes_map.items():
        target = f"WV.T.{_base(b)}"
        if a not in emitted:
            adopt(a, target)
        events.append({"event_id": f"WV.act.{b}", "type": "supersede", "target": target,
                       "option": f"o{b}", "supersedes": f"o{a}", "authority_level": "product",
                       "scope": "wevolley", "valid_at": by_id[b]["date"], "recorded_at": by_id[b]["date"],
                       "title": by_id[b]["title"]})
        emitted.add(b)

    # pass 2: standalone + flag unresolved relations
    for e in entries:
        if e["partial"] and e["superseded_by"]:
            flagged.append(f"{e['id']} partial→{e['superseded_by']} ({e['title']}) — 축 분해 adjudication 필요")
        if e["id"] not in emitted:
            adopt(e["id"], f"WV.T.{e['id']}")

    events.sort(key=lambda x: (x["valid_at"], x["event_id"]))
    return events, flagged


if __name__ == "__main__":
    md = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MD
    entries = parse(md)
    events, flagged = build(entries)
    print(f"# AUTO-EXTRACTED from {md} — {len(entries)} decisions, {len(events)} events")
    print(f"# 제목-마커 full-supersede만 신뢰. 아래 flagged는 owner adjudication 필요:")
    for f in flagged:
        print(f"#   FLAG: {f}")
    print(yaml.safe_dump({"events": events}, allow_unicode=True, sort_keys=False))
