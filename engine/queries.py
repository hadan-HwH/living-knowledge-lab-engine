"""Query semantics over the A- and S-projections (representation-method §7).

Phase 1 implements the A-axis queries; O2 adds §7.2 OPTION_EVIDENCE_PROFILE.
I/H queries come with later stages.
"""
from __future__ import annotations

from reducer import project_authority, DECISION_ACT_TYPES
from evidence import evidence_profile


def current_authority(events, target, valid_at, known_at, scope=None):
    """§7.1 CURRENT_AUTHORITY — the officially active decision as of (valid_at, known_at).

    Low evidence never excludes an active decision here (that is S/H's job, not A's).
    """
    proj = project_authority(events, target, valid_at, known_at, scope)
    return {
        "current_option": proj["current_option"],
        "current_state": proj["current_state"],
        "active_options": proj["active_options"],
        "exceptions": proj["exceptions"],
        "states": proj["states"],
    }


def project_all(events, valid_at, known_at, scope=None):
    """§7.7-ish DECISION_SNAPSHOT — the active decision set across every target, as of (valid_at, known_at).

    "지금 프로젝트가 뭘 결정해 놨는가" — the history laid down as a base.
    """
    targets = sorted({e["target"] for e in events if e.get("type") in DECISION_ACT_TYPES})
    active, superseded_or_inactive, conflicts = [], [], []
    for t in targets:
        p = project_authority(events, t, valid_at, known_at, scope)
        if p["current_state"] == "authority_conflict":
            conflicts.append(t)
        for opt, st in p["states"].items():
            row = {"target": t, "option": opt, "state": st}
            (active if st == "active" else superseded_or_inactive).append(row)
    return {
        "as_of": {"valid_at": valid_at, "known_at": known_at},
        "active_count": len(active),
        "active": sorted(active, key=lambda r: r["target"]),
        "inactive": sorted(superseded_or_inactive, key=lambda r: r["target"]),
        "conflicts": conflicts,
    }


def option_evidence_profile(events, target, valid_at, known_at, scope=None):
    """§7.2 OPTION_EVIDENCE_PROFILE — per-option A state + S ledger, no "best option" synthesis.

    Two contracts made visible here (representation-method §4.2/§7.2):
      - S never changes A: a supported option can be revoked, a challenged one can stay active.
      - No aggregation rule is frozen, so there is no BEST_SUPPORTED_OPTION derivation.
    """
    proj = project_authority(events, target, valid_at, known_at, scope)
    opts = set(proj["states"])
    opts.update(e.get("subject_ref") for e in events
                if e.get("type") == "EvidenceEvent" and e.get("target") == target)
    profile = {}
    for opt in sorted(o for o in opts if o):
        s = evidence_profile(events, opt, valid_at, known_at, target)
        profile[opt] = {
            "authority_state": proj["states"].get(opt, "none"),
            "derived_label": s["derived_label"],
            "support_groups": s["support_groups"],
            "attack_groups": s["attack_groups"],
            "supporting_evidence": s["supporting_evidence"],
            "attacking_evidence": s["attacking_evidence"],
        }
    return {"target": target, "current_option": proj["current_option"], "options": profile}


def open_decisions(events, valid_at, known_at, scope=None):
    """§2 T9 OPEN_DECISION — 지금 열려 있는(미결) 결정은 무엇인가.

    핵심 판별(deferral gold): '보류' 라벨은 두 가지를 섞는다 —
      결정 확정·조항화만 보류(I축, T11)  → 현행 있음 → open 아님
      결정 내용 자체 미결(defer/candidate) → 현행 없음 → open
    metadata(status='보류')로는 못 가르고 A-reducer 상태로만 갈린다.
    open = 활성 현행이 없고(candidate/deferred만) 제안·보류 이력이 있는 target."""
    targets = sorted({e["target"] for e in events if e.get("type") in DECISION_ACT_TYPES})
    open_items = []
    for t in targets:
        p = project_authority(events, t, valid_at, known_at, scope)
        if p["current_state"] == "active":
            continue                                  # 결정 확정 → open 아님
        deferred = sorted(o for o, s in p["states"].items() if s in ("deferred", "candidate"))
        if not deferred:
            continue                                  # 미결 옵션 없음(revoked/rejected뿐) → open 아님
        triggers = sorted({e["resume_trigger"] for e in events
                           if e.get("target") == t and e.get("resume_trigger")
                           and e.get("recorded_at", "") <= known_at})
        open_items.append({"target": t, "deferred_options": deferred,
                           "resume_triggers": triggers, "current_state": p["current_state"]})
    return {"as_of": {"valid_at": valid_at, "known_at": known_at},
            "open": open_items, "open_count": len(open_items)}


def history_rationale(events, target, known_at, scope=None):
    """§7.4 HISTORY_RATIONALE — the ordered act timeline (inactive/superseded included on purpose)."""
    # valid_at set to the far future so every recorded act (<= known_at) is folded in.
    proj = project_authority(events, target, valid_at="9999-12-31", known_at=known_at, scope=scope)
    return {
        "timeline": proj["decision_chain"],
        "final_states": proj["states"],
        "current_option": proj["current_option"],
    }
