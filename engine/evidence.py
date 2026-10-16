"""S-axis reducer (Phase 1, O2 = A+S) — folds EvidenceEvents into an evidence profile.

Per representation-method v0.3 §4.2/§6.2:
  - Only EvidenceEvents update S; DecisionActs and ImplementationObservations never do.
  - subject_ref is exactly one option or proposition (invariant #30 — no dual counting).
  - Repeated citations of the same source span are ONE independence group, not N evidences.
  - No numeric score. derived_label comes from the frozen rule below (§4.2 "사전 동결한 규칙").
  - Absence of evidence is `unknown`, never `challenged` (증거 부재는 반증이 아니다).
  - trend is NOT computed here — it needs 2+ frozen checkpoints per subject (§4.2), which
    Phase 1 gold does not have. Callers get the ledger; trend stays out of O2 v0.

Frozen derived_label rule (v0 — counting independence groups, not raw events):
  no groups                ->  unknown
  support only             ->  supported
  attack only              ->  challenged
  both support and attack  ->  mixed
"""
from __future__ import annotations


def _evidence_events(events, subject_ref, valid_at, known_at, target=None):
    """Bitemporal filter: observed_at is world-time, recorded_at is knowledge-time."""
    seen, out = set(), []
    for e in events:
        if e.get("type") != "EvidenceEvent":
            continue
        if e.get("subject_ref") != subject_ref:
            continue
        if target is not None and e.get("target") != target:
            continue
        if str(e.get("recorded_at", "")) > str(known_at):
            continue
        if str(e.get("observed_at", "")) > str(valid_at):
            continue
        eid = e["event_id"]
        if eid in seen:                      # idempotency (invariant #4)
            continue
        seen.add(eid)
        out.append(e)
    return out


def evidence_profile(events, subject_ref, valid_at, known_at, target=None):
    """§4.2 S — the evidence ledger and frozen-rule label for one subject as of (valid_at, known_at)."""
    evs = _evidence_events(events, subject_ref, valid_at, known_at, target)

    # independence groups: events citing the same span share a group and count once.
    # An event without independence_group is its own group (annotator declares grouping).
    support_groups, attack_groups = set(), set()
    for e in evs:
        group = e.get("independence_group") or e["event_id"]
        if e.get("polarity") == "support":
            support_groups.add(group)
        elif e.get("polarity") == "attack":
            attack_groups.add(group)

    if not support_groups and not attack_groups:
        label = "unknown"
    elif not attack_groups:
        label = "supported"
    elif not support_groups:
        label = "challenged"
    else:
        label = "mixed"

    return {
        "subject_ref": subject_ref,
        "supporting_evidence": sorted(e["event_id"] for e in evs if e.get("polarity") == "support"),
        "attacking_evidence": sorted(e["event_id"] for e in evs if e.get("polarity") == "attack"),
        "support_groups": len(support_groups),
        "attack_groups": len(attack_groups),
        "derived_label": label,
    }
