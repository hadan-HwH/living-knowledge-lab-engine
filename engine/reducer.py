"""A-axis reducer (Phase 1) — folds DecisionActs into an authority projection.

Scope: authority (A) only, per representation-method v0.3 §4.1/§6.1.
Evidence (S) and Implementation (I) events are loaded but ignored by this fold.
This is the O0 baseline (PPIR-equivalent) that later stages (O2 = A+S) build on.

No S=0.72-style scores, no ontology, no auto-transition beyond the §6.1 contract.
"""
from __future__ import annotations

from pathlib import Path
import yaml

AUTHORITY_RANK = {"proposal": 0, "team": 1, "product": 2, "executive": 3}

DECISION_ACT_TYPES = {
    "propose", "adopt", "defer", "suspend", "resume", "reject",
    "revoke", "supersede", "re_adopt", "amend",
    "narrow_scope", "expand_scope", "confirm_current",
}

INACTIVE_STATES = {"deferred", "rejected", "revoked", "superseded"}


def load_events(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return data.get("events", [])


def _scope_matches(event_scope, query_scope):
    """Hierarchical scope match: one path is a prefix of the other (segments by '/')."""
    if query_scope is None or event_scope is None:
        return True
    if event_scope == query_scope:
        return True
    e = event_scope.split("/")
    q = query_scope.split("/")
    n = min(len(e), len(q))
    return e[:n] == q[:n]


def _scope_covers(covering_scope, covered_scope):
    """Directional: covering_scope governs covered_scope (covering is an ancestor-or-equal path)."""
    if covering_scope is None:
        return True
    if covered_scope is None:
        return False
    c = covering_scope.split("/")
    q = covered_scope.split("/")
    return len(c) <= len(q) and q[:len(c)] == c


def project_authority(events, target, valid_at, known_at, scope=None):
    """Fold DecisionActs for one target into the authority state as of (valid_at, known_at).

    Invariants enforced (representation-method §9):
      #4  idempotency      — duplicate event_id folded once
      #7  bitemporal safety — recorded_at > known_at is invisible; valid_at > valid_at not yet in effect
      #8  scope preservation — only scope-matching acts apply
      #9  conflict visibility — >1 incompatible active option => authority_conflict (no arbitrary winner)
    """
    seen = set()
    acts = []
    for e in events:
        if e.get("type") not in DECISION_ACT_TYPES:
            continue
        if e.get("target") != target:
            continue
        if str(e["recorded_at"]) > str(known_at):     # transaction-time cutoff
            continue
        if str(e["valid_at"]) > str(valid_at):         # valid-time cutoff
            continue
        if not _scope_matches(e.get("scope"), scope):
            continue
        eid = e["event_id"]
        if eid in seen:                                # idempotency / dedup
            continue
        seen.add(eid)
        acts.append(e)

    # deterministic fold order (§6.1): valid_at (decision_time) primary,
    # recorded_at aux, event_id final tiebreak. ISO date strings sort correctly.
    acts.sort(key=lambda e: (str(e["valid_at"]), str(e.get("recorded_at", "")), e["event_id"]))

    states = {}          # option -> A.state
    authority_of = {}    # option -> authority rank that last set it active
    scope_of = {}        # option -> event scope of the act that last set it active
    exception_of = {}    # option -> the general option it explicitly overrides (act's exception_to)
    chain = []
    for e in acts:
        t = e["type"]
        opt = e.get("option")
        rank = AUTHORITY_RANK.get(e.get("authority_level", "product"), 2)

        if t == "propose":
            states.setdefault(opt, "candidate")
        elif t == "adopt":
            if _blocked_by_higher_authority(states, authority_of, opt, rank):
                pass  # lower authority cannot override a higher-authority active option
            else:
                states[opt] = "active"
                authority_of[opt] = rank
                scope_of[opt] = e.get("scope")
                if e.get("exception_to"):
                    # annotator-declared narrow-scope override (§4 exception) —
                    # the reducer never infers this from scope shape alone
                    exception_of[opt] = e["exception_to"]
        elif t == "defer":
            states[opt] = "deferred"
        elif t == "suspend":
            if states.get(opt) == "active":
                states[opt] = "suspended"
        elif t == "resume":
            if states.get(opt) == "suspended":
                states[opt] = "active"
                authority_of[opt] = rank
        elif t == "reject":
            states[opt] = "rejected"
        elif t == "revoke":
            if states.get(opt) in ("active", "suspended"):
                states[opt] = "revoked"
        elif t == "supersede":
            old = e.get("supersedes")
            if old is not None:
                states[old] = "superseded"
            states[opt] = "active"
            authority_of[opt] = rank
            scope_of[opt] = e.get("scope")
        elif t == "re_adopt":
            states[opt] = "active"
            authority_of[opt] = rank
        elif t == "confirm_current":
            pass  # no-op; the source/time is recorded on the chain only
        # amend / narrow_scope / expand_scope: no A-state change in the MVP —
        # semantic changes must arrive as a successor option + supersede (invariant #27).

        chain.append({
            "event_id": e["event_id"], "type": t, "option": opt,
            "valid_at": e["valid_at"], "reason_type": e.get("reason_type"),
        })

    active = sorted(o for o, s in states.items() if s == "active")

    # §4 exception semantics: an active option declared exception_to a *still-active*
    # general option is a scoped override, not a conflict. Conflict = >1 active generals.
    active_set = set(active)
    exceptions = sorted(o for o in active if exception_of.get(o) in active_set)
    generals = [o for o in active if o not in exceptions]
    conflict = len(generals) > 1

    current = None
    if not conflict and active:
        # the most scope-specific exception whose scope governs the query scope wins;
        # outside every exception scope (or with no query scope) the general rule holds
        governing = [o for o in exceptions if _scope_covers(scope_of.get(o), scope)] if scope else []
        if governing:
            current = max(governing, key=lambda o: len((scope_of.get(o) or "").split("/")))
        elif generals:
            current = generals[0]
        else:
            current = active[0]  # exceptions only (general no longer active) — plain active options

    return {
        "target": target,
        "valid_at": valid_at, "known_at": known_at, "scope": scope,
        "current_option": current,
        "current_state": ("authority_conflict" if conflict else ("active" if active else "none")),
        "active_options": active,
        "exceptions": {o: scope_of.get(o) for o in exceptions},
        "states": states,
        "decision_chain": chain,
    }


def _blocked_by_higher_authority(states, authority_of, opt, rank):
    """A lower-authority adopt cannot displace an option kept active by higher authority."""
    for other, st in states.items():
        if other != opt and st == "active" and authority_of.get(other, 2) > rank:
            return True
    return False
