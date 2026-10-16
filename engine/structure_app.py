"""canon-aware 구조화 파이프라인 오케스트레이터 — prep(앞단)/fold(뒷단) 결정론 코어.
사이의 Tier B 추출은 에이전트 단계(prep의 canon_context 주입). 설계: docs/2-method/canon-aware-structuring-pipeline-design.md."""
from __future__ import annotations
import re
from pathlib import Path
import yaml
from canon_select import select_canon
from corpus import (load_registry, canon_path, canon_dir, tier_a_path, work_dir,
                    concept_exclude_for, is_concept_excluded)
from ingest import doc_slug as _doc_slug
from doc_identity import realign_bodies
from l1_snapshot import _module_path
from parsers import parse, parse_markdown_sections


def _norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def statement_units(canon_concepts, app_scope, kinds):
    """S3a 입력 — 같은 scope의 **서술 단위 전문**. 결정론·LLM 0. (설계 §2-1)"""
    from body_probe import _texts_of
    out = []
    for c in canon_concepts or []:
        if c.get("kind") not in kinds or c.get("scope") != app_scope:
            continue
        texts = [{"key": k, "text": t} for k, t in _texts_of(c) if t]
        if not texts:
            continue
        # kind를 실어 보낸다 — 소비자가 조항과 화면을 갈라 볼 수 있어야 한다(`how`).
        row = {"anchor": c["anchor"], "kind": c.get("kind"), "texts": texts}
        if c.get("section"):
            row["section"] = c["section"]
        out.append(row)
    out.sort(key=lambda a: a["anchor"])
    return out


def _slim_canon(c):
    """canon-context.yaml 투영 — content/table/refs 등 무거운 필드 제거, head만 보존.
    head = content 첫 120자(공백 접기, 결정론). name/section은 있을 때만 포함."""
    out = {"anchor": c.get("anchor"), "kind": c.get("kind"), "scope": c.get("scope")}
    if c.get("name"):
        out["name"] = c["name"]
    if c.get("section"):
        out["section"] = c["section"]
    if c.get("tier"):
        # ★계약 §1b가 명시한 신호 — 지난 회차에 정본화한 개념(B)과 원문 조항(A)의 구분.
        out["tier"] = c["tier"]
    if c.get("tier") != "B":
        # Tier B는 head를 싣지 않는다 — 계약상 `name`이 "개념명+짧은 설명"이라 중복이고,
        # 개념 수백 건 × 120자면 수십 K자다. 조항(Tier A)은 이름이 없어 head가 유일한 단서라 남긴다.
        out["head"] = _norm_ws(c.get("content") or "")[:120]
    return out


# ── S0 ingest — 새 앱 sections.yaml 기계 생성 초안 (마지막 다리, Task 11) ────────
# 지금까지 probe sections.yaml은 수기 저작(VERBATIM copies)이었다. 새 앱을 파이프라인에
# 태우려면 문서 코퍼스의 spec.md 계열 문서에서 verbatim 섹션 초안을 기계 생성해야 한다.
# 범용 어댑터 parsers.parse_markdown_sections를 무수정 재사용 — 여기선 문서별 doc_slug을
# 넣어 호출하는 배선과 파일 I/O만 담당한다(의미 추론·재서술 없음).


def run_ingest(source_files, app_scope, fmt="markdown-sections"):
    """[(doc_rel_path, md_text), ...] → probe sections 스키마 [{anchor, doc, text}, ...].
    parse_markdown_sections를 문서마다 doc_slug=ingest.doc_slug(doc_rel_path)로 호출(무수정
    재사용) — 앵커가 <doc_slug>#<heading_slug> 형태라 문서 간 충돌이 자동으로 사라진다
    (별도 접두 로직 불필요). text는 원문 raw 슬라이스(해당 섹션의 헤딩 줄부터 다음 섹션
    직전까지, md_text.splitlines()에서 어댑터가 이미 매긴 line 경계로 자름) — 어댑터의
    content 필드(헤딩 제외·개념 본문만)가 아니라 **헤딩 포함 원문 그대로**를 쓴다. 기존
    수기 probe(sections.yaml)가 "## 헤딩

본문" 형태로 헤딩까지 포함해온 관례와
    맞추기 위함 — 재서술·요약 없이 원문을 그대로 옮기는 게 §8 왕복 게이트의 진실
    원천이라는 목표에 더 맞는다. 순서: source_files가 준 문서 순서 → 문서 내 등장 순서
    (둘 다 입력/어댑터가 이미 보존 — 정렬을 추가로 걸면 등장 순서가 깨진다)."""
    out = []
    code_fmt = str(fmt).startswith("code-symbols")
    for rel_path, text_src in source_files:
        lines = text_src.splitlines()
        concepts = parse(fmt, text_src, scope=app_scope,
                         doc_slug=_doc_slug(rel_path),
                         module=_module_path(rel_path))["concepts"]
        if code_fmt:
            for c in concepts:
                f = c.get("fields") or {}
                parts = [f.get("signature"), c.get("content"), f.get("comments")]
                out.append({"anchor": c["anchor"], "doc": rel_path,
                            "text": "\n".join(x for x in parts if x).strip()})
            continue
        # 줄 순서로 자른다 — 코드는 중첩(모듈⊃클래스⊃메서드)이라 등장 순서가 곧 경계다.
        # 마크다운은 어댑터가 이미 줄 순서로 내므로 무변화(정렬이 no-op).
        concepts = sorted(concepts, key=lambda c: c.get("line") or 0)
        for i, c in enumerate(concepts):
            start = (c.get("line") or 1) - 1
            end = (concepts[i + 1].get("line") or 1) - 1 if i + 1 < len(concepts) \
                else len(lines)
            text = "\n".join(lines[start:end]).strip("\n")
            out.append({"anchor": c["anchor"], "doc": rel_path, "text": text})
    return out


_INGEST_HEADER = ("# 기계 생성 초안(run_ingest) — verbatim, 검토 후 사용\n"
                  "# parse_markdown_sections 어댑터 원문 그대로. 정본 편입 전 검토 필요.\n")


def run_ingest_cli(source_root, src_rel, out_dir, app_scope, force=False, exclude=(),
                   formats=None):
    """corpus source(source_root) 기준 상대경로 src_rel 아래 *.md를 재귀·정렬 순회해
    run_ingest로 초안을 만들고 out_dir/sections.yaml에 저장. doc 필드는 source_root
    기준 상대경로(기존 수기 probe 관례와 동일 — 예: cargo sections.yaml의
    "doc: 3-prime-commerce/..."). 기존 파일이 있으면 SystemExit(수기 저작물 보호) —
    force=True(CLI --force)일 때만 덮어쓴다."""
    source_root = Path(source_root)
    out_dir = Path(out_dir)
    out_path = out_dir / "sections.yaml"
    if out_path.exists() and not force:
        raise SystemExit(f"거부: {out_path} 이미 존재(수기 저작물 보호) — --force로 덮어쓰기")
    src_dir = source_root / src_rel
    if formats:
        pairs = []
        for g, fmt in sorted(formats.items()):
            for f in sorted(source_root.glob(g)):
                if not f.is_file():
                    continue
                rel = f.relative_to(source_root)
                if src_rel not in (".", "") and not str(rel).startswith(str(src_rel)):
                    continue
                if is_concept_excluded(rel, exclude):
                    continue
                pairs.append((str(rel), fmt))
        seen, ordered = set(), []
        for rel, fmt in pairs:                      # 같은 파일이 두 글롭에 걸리면 첫 선언
            if rel not in seen:
                seen.add(rel)
                ordered.append((rel, fmt))
        secs = []
        for rel, fmt in ordered:
            secs.extend(run_ingest([(rel, (source_root / rel).read_text(encoding="utf-8"))],
                                   app_scope, fmt=fmt))
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(_INGEST_HEADER)
            yaml.safe_dump({"sections": secs}, fh, allow_unicode=True, sort_keys=False)
        by_fmt = {}
        for _, fmt in ordered:
            by_fmt[fmt] = by_fmt.get(fmt, 0) + 1
        print(f"ingest {app_scope}: {len(secs)}개 단위({len(ordered)}개 파일 {by_fmt})"
              f" → {out_path}")
        return secs
    files = sorted(src_dir.rglob("*.md"))
    kept = [f for f in files if not is_concept_excluded(f.relative_to(source_root), exclude)]
    dropped = len(files) - len(kept)
    source_files = [(str(f.relative_to(source_root)), f.read_text(encoding="utf-8"))
                    for f in kept]
    secs = run_ingest(source_files, app_scope)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(_INGEST_HEADER)
        yaml.safe_dump({"sections": secs}, fh, allow_unicode=True, sort_keys=False)
    _ex = f" · 제외 {dropped}개 문서({', '.join(exclude)})" if dropped else ""
    print(f"ingest {app_scope}: {len(secs)}개 섹션({len(source_files)}개 문서){_ex} → {out_path}")
    return secs


# ── S1 prep — new_sections+canon 선택 → 추출 지시 결정 코어 (prep_plan) ─────────
# I/O 다리(sections.yaml 로드, canon-context.yaml/extract-manifest.yaml 저장)는
# run_prep(아래, cost_summary 다음)이 담당 — 여기 prep_plan 자체는 순수함수.


def prep_plan(app_scope, new_sections, canon_concepts, prev_sections=None,
              shared_tiers=("foundations",), merged_scopes=(), archive_segments=()):
    """S0 ingest 결과(new_sections) + S1 정본 선택 → 추출 지시.
    new_sections=[{anchor,text,...}] · canon_concepts=[{anchor,name,scope,...}].
    prev_sections=None이면 첫 실행(전부 추출), 아니면 증분(바뀐 섹션만).
    removed=prev_sections 원본 dict(정규화 안 됨). 섹션 리스트는 단일 앱 호출 가정
    (anchor로 필터 — 다중 scope 혼합 금지).
    반환: to_extract/carried/removed/canon_context."""
    if prev_sections is None:
        to_extract, carried, removed, moved = list(new_sections), [], [], []
    else:
        from l1_integrity import snapshot_diff, classify_removed_units
        # l1_integrity.snapshot_diff는 (kind, scope, anchor) 키로 added/removed/changed를
        # 가르고 (content, values) 튜플로 변경을 판정한다(engine/l1_integrity.py 참고).
        # 실 probe sections.yaml은 anchor/doc/text뿐(kind/scope/content 없음)이라 정규화
        # 없이 넣으면 전건 added로 오판된다 — kind/scope는 기본값으로 채우고 content가
        # 없으면 text로 대체한다. content는 공백/개행 정규화(subconcept._norm과 동일
        # 관례) 후 비교 — 안 그러면 재포맷만으로도 changed 오판되어 Tier B가 불필요하게
        # 재호출된다("적은 비용" 목표 위반).
        def _norm(s):
            content = s.get("content", s.get("text"))
            return {"kind": s.get("kind", "probe_section"),
                    "scope": s.get("scope", app_scope), "anchor": s["anchor"],
                    # 이동 판정의 1차 축. ★원장(sections.yaml)은 `file`이 아니라 `doc`을
                    # 쓴다 — 둘을 안 이으면 분류기의 파일 축이 실 파이프라인에서만 조용히
                    # 죽는다(합성 테스트는 file을 직접 넣어 통과한다).
                    "file": s.get("file") or s.get("doc"),
                    "content": _norm_ws(content) if content is not None else content}

        diff = snapshot_diff([_norm(s) for s in prev_sections],
                             [_norm(s) for s in new_sections])
        cls = classify_removed_units(diff["removed"], diff["added"],
                                     archive_segments=archive_segments)
        moved = cls["moved"]
        moved_to = {m["to"] for m in moved}
        # 내용이 같은 **순수 이동**은 재추출하지 않는다 — 자리만 바뀐 같은 지식이라
        # LLM을 다시 부를 이유가 없다("적은 비용" 목표). 옮기며 고쳤으면 changed로 남는다.
        prev_content = {c["anchor"]: c.get("content") for c in
                        (_norm(s) for s in prev_sections)}
        new_content = {c["anchor"]: c.get("content") for c in
                       (_norm(s) for s in new_sections)}
        pure_moves = {m["to"] for m in moved
                      if prev_content.get(m["from"]) == new_content.get(m["to"])}
        changed_anchors = ({c["anchor"] for c in diff["added"]} |
                           {c["anchor"] for c in diff["changed"]}) - pure_moves
        removed_anchors = {r["anchor"] for r in cls["renamed_or_deleted"]}
        to_extract = [s for s in new_sections if s["anchor"] in changed_anchors]
        carried = [s for s in new_sections if s["anchor"] not in changed_anchors]
        removed = [s for s in prev_sections if s["anchor"] in removed_anchors]
    canon_context = select_canon(app_scope, to_extract, canon_concepts, shared_tiers,
                                 merged_scopes=merged_scopes)
    return {"to_extract": to_extract, "carried": carried, "removed": removed,
            "moved": moved, "canon_context": canon_context}


# ── S3 fold — 추출 결과(align-proposals) 검증→자동 병합·판정 큐 결정 코어 ───────
# I/O 다리(align-proposals.yaml/subconcepts.yaml 로드, §8 왕복 게이트, adjudication.yaml
# 저장)는 run_fold(아래, cost_summary 다음)가 담당 — 여기 fold_plan 자체는 순수함수.


#: align_concepts가 "정본에 없는 대상"에 붙이는 사유 접두 — 이 종류만 배치 치명에서
#: 항목 격리로 강등한다(구조 오류: phantom sid·중복·누락은 배치 속성이라 그대로 치명).
_PHANTOM_TARGET_REASON = "정본 인덱스에 없는 대상"


def fold_plan(app_scope, proposals, subconcepts, canonical_index, prev_dispositions=None,
              full_index=None, deep_index=None):
    """S3 align(검증) → merged 자동 fold · new/ambiguous 판정 큐. 결정론.
    proposals: 추출기 산출 [{sid, target, confidence, evidence?}] — sid는 이미 '<scope>#anchor'.
    subconcepts: [{anchor,...}] (전건 커버 대조용 — 명단은 여기서 유도, proposals에서 유도하면
    누락 제안이 그냥 사라져 전건 커버 검증이 무력화된다). canonical_index: 유효 정본 앵커 집합.
    prev_dispositions={sid: 판정dict} — 이번 proposals에 없는 sid만 이월(멱등).
    계약: errors>0이면 auto_fold=[](fail-closed — 배치 무결성 깨짐, 전건 판정행). errors>0 시
    merged는 was=merged_blocked로 큐 편입(전건 판정행 실제 성립).
    반환: align(원 보고)/auto_fold(merged, errors=0일 때만)/
    adjudication_queue(new+ambiguous(+errors>0일 때 merged_blocked), target/confidence/
    evidence/downgraded 등 판정 맥락 보존, sid 정렬)/carried_dispositions(이번 proposals에
    없는 이전 판정, 재판정 0)."""
    from concept_align import align_concepts
    new_subs = {f"{app_scope}#{s['anchor']}" for s in subconcepts}
    # 유효 대상 = 주입 canon(canonical_index) ∪ 전체 스냅샷(full_index).
    injected = set(canonical_index)
    valid_targets = injected | set(full_index or ())
    a = align_concepts(proposals, valid_targets, new_subs)
    merged = [{**m, "cross_scope": True} if m.get("target") not in injected else m
              for m in a["merged"]]
    # 지어낸 대상은 그 항목만 격리한다(게이트 격리 원칙과 동형) — 배치는 안 막는다.
    # 구조 오류(phantom sid·중복 제안·미제안)는 배치 속성이라 종전대로 치명.
    phantom = [e for e in a["errors"] if str(e.get("reason", "")).startswith(_PHANTOM_TARGET_REASON)]
    a["errors"] = [e for e in a["errors"] if e not in phantom]
    a["stats"]["errors"] = len(a["errors"])
    # ★개념은 조항에 병합되지 않는다 — 조항은 개념이 나타난 자리지 개념이 아니다.
    # deep_index(정본 깊은층 anchor 집합)를 주면 그 밖으로의 merged는 재관측이 아니라
    article_only = []
    if deep_index is not None:
        deep = set(deep_index)
        article_only = [m for m in merged if m.get("target") not in deep]
        merged = [m for m in merged if m.get("target") in deep]
    auto_fold = list(merged) if not a["errors"] else []   # fail-closed(구조 오류만)
    queue = [{**x, "was": "new"} for x in a["new"]] + \
            [{**x, "was": "ambiguous"} for x in a["ambiguous"]] + \
            [{**x, "was": "article_only"} for x in article_only] + \
            [{**x, "was": "phantom_target"} for x in phantom]
    if a["errors"]:
        queue += [{**x, "was": "merged_blocked"} for x in merged]
    # ★소유자 판정 재부착 — 재제안된 sid의 판정은 살아남는다.
    prior = prev_dispositions or {}
    _JUDGMENT_KEYS = ("disposition", "align_to", "needs_review", "removed_at")
    queue = [{**q, **{k: prior[q["sid"]][k] for k in _JUDGMENT_KEYS
                      if k in prior.get(q["sid"], {})}} for q in queue]
    queue.sort(key=lambda q: q["sid"])
    current = {p["sid"] for p in proposals}
    carried_dispositions = [v for k, v in sorted(prior.items()) if k not in current]
    return {"align": a, "auto_fold": auto_fold, "adjudication_queue": queue,
            "carried_dispositions": carried_dispositions}


def _quote_owner_anchors(sub, sections):
    """이 subconcept의 quote가 부분문자열로 들어 있는 섹션 anchor들.
    §8 왕복 게이트가 "quote는 sections 원문의 부분문자열"을 강제하므로, 이 역조회는
    **결정론이고 지어냄이 아니다** — 귀속 필드를 새로 만드는 게 아니라 이미 성립하는
    불변식을 읽는 것이다(빈 결과 = 이미 낡은 quote, 게이트가 잡을 몫)."""
    q = sub.get("quote")
    if not q:
        return set()
    return {s["anchor"] for s in sections if q in s.get("text", "")}


def merge_carried_subconcepts(new_subconcepts, prev_subconcepts, sections=None,
                              changed_anchors=None):
    """증분 fold 입력 병합 — 재추출(new_subconcepts)에 없는 이전 anchor만 이월.
    ★계약이 plan과 다름(주의): 애초 설계는 "quote 출처 섹션이 carried에 속하는 것만
    이월"이었으나 subconcept 레코드에는 출처 섹션 anchor 필드가 없다(quote만 있음) —
    결정론으로 귀속 불가한 것을 지어내지 않는다. 대신 fold_plan의 sid 기준 이월과
    동형인 단순 계약을 쓴다: prev_subconcepts 중 anchor가 new_subconcepts에 없는 것만
    이월(재추출분이 항상 우선). carried_anchors 파라미터는 이 결정으로 불필요해져 뺐다.
    ★한계: 재추출 섹션에서 에이전트가 더 이상 뽑지 않은(사라진) 개념이 removed 처리
    없이 이월분에 그대로 남을 수 있다 — 이 함수 자체는 그 판단을 하지 않는다. §8
    왕복 게이트(verify_subconcepts, run_fold에 배선)가 이월분의 quote 유효성은 감시하지만
    "왜 이번엔 안 뽑혔는가"는 별개 후속 과제. 이 침식 벡터는 l1_integrity의
    dead_ref_report류가 개념층에서 잡는 것과 동형 — subconcept층엔 아직 대응 감시 없음
    (후속). 결정론(anchor 정렬)."""
    new_anchors = {s["anchor"] for s in new_subconcepts}
    carried = []
    for s in prev_subconcepts:
        if s["anchor"] in new_anchors:
            continue
        if sections is not None and changed_anchors:
            owners = _quote_owner_anchors(s, sections)
            if owners and owners <= set(changed_anchors):
                continue          # 재추출 섹션 소유 = 대체됨
        carried.append(s)
    out = list(new_subconcepts) + carried
    out.sort(key=lambda s: s["anchor"])
    return out


def prior_anchor_hints(prev_subconcepts, prev_sections):
    """이전 회차 섹션별 개념 명단 — {섹션 anchor: [{anchor, name}]}. 결정론(anchor 정렬).

    귀속은 지어내지 않는다 — quote 역조회다. 왕복 게이트가 "quote ⊂ 섹션 원문"을 이미
    강제하므로 **이전** 섹션 원문에서 소유 섹션을 되찾는 건 결정론이다. 이전 섹션 어디에도
    quote가 없는(이미 낡은) 개념은 힌트에서 빠진다 — 없는 계보를 만들지 않는다."""
    hints = {}
    for s in sorted(prev_subconcepts, key=lambda x: x["anchor"]):
        for owner in sorted(_quote_owner_anchors(s, prev_sections)):
            hints.setdefault(owner, []).append({"anchor": s["anchor"], "name": s.get("name")})
    return hints


def split_removed_subconcepts(subconcepts, sections, removed_sections, at):
    """섹션 삭제 → 개념 tombstone. (살아있는 것, 삭제 표시된 것) 반환. 결정론(anchor 정렬).

    ★코퍼스 관행과의 구분(중요): 문서 코퍼스 규약은 "조항 삭제 금지, `(폐기: D-1093)`로 결번"
    이라 폐기는 텍스트가 남는다 → prep이 `changed`로 잡아 재추출한다(여기 경로 아님).
    이 함수가 상대하는 건 섹션·파일이 통째로 사라지는 경우다(아카이브 이관·앱 통합·폴더 삭제).

    규율 — 증명 가능한 삭제만 표시한다: quote가 삭제된 섹션 원문에 실재했음을
    역조회(_quote_owner_anchors)로 확인한 것만 tombstone. 어디서도 못 찾은 것은
    지어내지 않고 살려 보내 게이트가 판정하게 한다(조용한 소실 금지)."""
    live, tombs = [], []
    for s in sorted(subconcepts, key=lambda x: x["anchor"]):
        if _quote_owner_anchors(s, sections):
            live.append(s)
            continue
        owners = _quote_owner_anchors(s, removed_sections or [])
        if owners:
            tombs.append({**s, "removed_at": at, "removed_from": sorted(owners)})
        else:
            live.append(s)          # 출처 미상 — 게이트 몫
    return live, tombs


def merge_carried_proposals(new_proposals, prev_proposals, subconcepts, app_scope):
    """증분 fold 입력 병합 — align-proposals의 이월 축(merge_carried_subconcepts의 짝).
    ★왜 필요한가(실 2회차가 드러낸 갭): 재추출 에이전트는 **바뀐 섹션의 proposal만**
    낸다. subconcept만 이월하면 이월분이 전부 `align_concepts`의 "미제안(누락)" error가
    되고, fold_plan은 errors>0에서 fail-closed라 **배치 전체가 막힌다**. 계약 문서
    (extraction-handoff-contract §1c)는 "이월분은 fold가 merge_carried_subconcepts로
    병합"이라고만 적었는데, 실제로는 proposal 축이 하나 더 필요했다(문서-구현 갭).
    규칙: sid 기준 재추출분 우선, 이번에 없는 sid만 이전 것에서 이월. 병합된 subconcept
    명단(subconcepts) 밖 sid는 버린다 — 안 그러면 phantom sid error가 난다. 결정론(sid 정렬)."""
    valid = {f"{app_scope}#{s['anchor']}" for s in subconcepts}
    by_sid = {p["sid"]: p for p in prev_proposals if p.get("sid") in valid}
    by_sid.update({p["sid"]: p for p in new_proposals if p.get("sid") in valid})
    return [by_sid[k] for k in sorted(by_sid)]


def cost_summary(prep, model=None, tokens=None, input_tokens=None,
                 output_tokens=None, cache_creation_tokens=None,
                 cache_read_tokens=None):
    """§9-B(v1 개정: 비용=AI 모델 비용) Track R 입력 — 호출 수(=추출 섹션)·모델·토큰.
    운영 실행마다 축적 → 모델 사다리 실험(티어별 게이트 통과율 vs 비용)의 원료.

    ★input/output 분할(input_tokens·output_tokens)은 §9-B 비용 게이트에 load-bearing:
    cost_ladder가 정밀 $/target를 내려면 입·출력 단가가 달라 분할이 필요하다(합계 tokens만
    으론 [전량input,전량output] 범위밖에 못 냄). 분할을 알면 기록할 것(cost_ladder 입력)."""
    out = {"tier_b_calls": len(prep.get("to_extract", [])),
           "carried": len(prep.get("carried", [])),
           "removed": len(prep.get("removed", []))}
    if model is not None:
        out["model"] = model
    if tokens is not None:
        out["tokens"] = tokens
    if input_tokens is not None:
        out["input_tokens"] = input_tokens
    if output_tokens is not None:
        out["output_tokens"] = output_tokens
    # 캐시 축 — 실 로그에서 입력 대부분이 캐시 읽기(0.1× 단가)였다. 이 분할 없이는
    # $/target이 크게 과대계상된다. cost_ladder.cost_per_target이 같은 키를 읽는다.
    if cache_creation_tokens is not None:
        out["cache_creation_tokens"] = cache_creation_tokens
    if cache_read_tokens is not None:
        out["cache_read_tokens"] = cache_read_tokens
    return out


def run_prep(base_dir, app_scope, snap_concepts, prev_sections=None, snap=None,
             prev_subconcepts=None, stack=None, corpus=None, force_extract=False,
             registry=None):
    """sections.yaml 로드 → prep_plan → canon-context.yaml + extract-manifest.yaml 저장.
    extract-manifest.yaml(계약: extraction-handoff-contract.md §1c) = 어느 anchor만
    추출할지의 기계 판독 선언 — 추출 에이전트가 to_extract만 보고, carried/removed는
    건드리지 않게 하는 유일한 영속 신호(이전엔 CLI 실행 컨텍스트에만 존재해 재현 불가였다)."""
    base_dir = Path(base_dir)
    secs = yaml.safe_load(open(base_dir / "sections.yaml"))["sections"]
    # 정본에 이미 올라간 개념을 추출 시점에 보여준다. 이게 없으면 추출기는 자기가 지난
    # 회차에 정본화한 개념을 매번 NEW로 다시 제안한다(갱신이 아니라 재생성).
    from canon_store import merge_canon
    canon_all = merge_canon(snap_concepts, stack) if stack else snap_concepts
    # registry 선언 — 개념 우주를 공유하는 scope(예: inv ∪ inv-system). 앱 단위 좁히기가
    # 이 선언을 깨지 않도록 여기서 넘긴다(종전엔 제품군 좁히기가 우연히 덮고 있었다).
    from corpus import concept_scope_merges_for, drop_excluded_sources
    merges = concept_scope_merges_for(corpus) if corpus else {}
    exclude = concept_exclude_for(corpus, registry) if corpus else ()
    canon_for_tier_b = drop_excluded_sources(canon_all, exclude)
    # 봉인 구역 선언 — 이동 목적지가 아카이브면 "현행에서 내리되 보존"으로 표시한다
    # (tombstone은 "없어졌다", archived는 "여기 있지만 현행이 아니다").
    from corpus import archive_segments_for
    plan = prep_plan(app_scope, secs, canon_for_tier_b, prev_sections=prev_sections,
                     merged_scopes=tuple(merges.get(app_scope) or ()),
                     archive_segments=archive_segments_for(corpus, registry) if corpus else ())
    # ★재추출 모드(벤치마크) — 문서가 안 바뀌어도 전건 추출하되 계보 힌트는 준다.
    # 평시 증분은 "안 바뀐 섹션은 재호출 0"이 맞지만(비용 목표), 그러면 prior_anchors도
    if force_extract:
        plan = {**plan, "to_extract": list(secs), "carried": []}
    cost = cost_summary(plan)
    # canon-context.yaml에는 슬림 투영만 기록(비용 목표) — plan["canon_context"]
    # 자체(반환값)는 원본 유지, 여기 파일 출력만 얇게 만든다.
    yaml.safe_dump({"canon": [_slim_canon(c) for c in plan["canon_context"]]},
                    open(base_dir / "canon-context.yaml", "w"),
                    allow_unicode=True, sort_keys=False)
    # S3a 입력 — 같은 scope 조항 전문(설계 §2-1). canon-context와 분리해 단계별로 준다.
    from corpus import statement_kinds_for
    arts = statement_units(canon_for_tier_b, app_scope,
                           statement_kinds_for(corpus, registry))
    # 파일 이름은 `articles.yaml` 그대로 둔다 — 내용은 일반화됐지만 경로를 바꾸면
    # 배선이 조용히 끊긴다(이번 감사에서 잡은 결함 3건이 전부 그 형태였다).
    yaml.safe_dump({"articles": arts}, open(base_dir / "articles.yaml", "w"),
                   allow_unicode=True, sort_keys=False)
    # 계보 힌트 — 재추출 대상 섹션에 한해 "지난 회차 이 섹션에서 나온 개념"을 싣는다
    # (이월 섹션은 재추출 자체가 없으므로 불필요). 추출 에이전트가 읽는 유일한 영속 신호.
    to_extract_anchors = {s["anchor"] for s in plan["to_extract"]}
    all_hints = prior_anchor_hints(prev_subconcepts or [], prev_sections or [])
    hints = {k: v for k, v in sorted(all_hints.items()) if k in to_extract_anchors}
    # fold의 3분류(P1-b) 재료 — 전체 스냅샷 앵커만(문자열 목록이라 가볍다).
    # "주입 밖이지만 실재"(교차앱 인용)를 "지어냄"과 가르는 유일한 근거다.
    yaml.safe_dump({"anchors": sorted({c["anchor"] for c in canon_all if c.get("anchor")})},
                    open(base_dir / "canon-full.yaml", "w"),
                    allow_unicode=True, sort_keys=False)
    yaml.safe_dump({"snap": snap,
                    "to_extract": sorted(to_extract_anchors),
                    "carried": sorted(s["anchor"] for s in plan["carried"]),
                    "removed": sorted(s["anchor"] for s in plan["removed"]),
                    # ★이동은 삭제가 아니다 — 침묵하면 "왜 anchor가 바뀌었나"의 근거가
                    # 사라져 다음 회차가 그걸 지어냄으로 오분류한다(침묵 소실 금지).
                    "moved": plan.get("moved") or [],
                    "prior_anchors": hints},
                    open(base_dir / "extract-manifest.yaml", "w"),
                    allow_unicode=True, sort_keys=False)
    # 삭제된 섹션의 **원문**을 남긴다 — manifest에 이름만 적으면 뒷단(fold)이 "이 개념이
    # 정말 그 섹션에서 왔는가"를 증명할 수 없어 삭제 표시를 지어내게 된다. 증거가 있어야
    # tombstone이 성립한다(split_removed_subconcepts).
    yaml.safe_dump({"at": snap, "sections": plan["removed"]},
                    open(base_dir / "removed-sections.yaml", "w"),
                    allow_unicode=True, sort_keys=False)
    # anchor 충돌로 주입에서 빠진 정본 기록(canon_select.canon_collisions) — canon-context는
    # anchor당 1행(=align target 공간)이라 소실이 불가피하지만, 침묵 소실은 감시 대상이다.
    from canon_select import canon_collisions
    collisions = canon_collisions(app_scope, plan["to_extract"], canon_all,
                                  merged_scopes=tuple(merges.get(app_scope) or ()))
    yaml.safe_dump({"collisions": collisions},
                    open(base_dir / "canon-collisions.yaml", "w"),
                    allow_unicode=True, sort_keys=False)
    print(f"prep {app_scope}: 추출대상 {len(plan['to_extract'])}"
          f" · 이월 {len(plan['carried'])} · canon 주입 {len(plan['canon_context'])}"
          f" · S3a 단위 {len(arts)}"
          f" · anchor 충돌 {len(collisions)} · cost {cost}")
    return plan, cost


def apply_quote_gate(app_scope, auto_fold, queue, gate):
    """§8 왕복 게이트 fail-closed 재매핑 — I/O 없는 순수함수(run_fold는 verify_subconcepts
    호출·결과 dump만 하고, 재매핑 로직 자체는 여기로 위임).
    gate = subconcept.verify_subconcepts(subs, sections) 반환값
    ({"ok": [...], "rejected": [{"anchor": ...}, ...]}).
    ★계약 개정: rejected는 **그 항목만 격리**한다 — 배치 전체를 막지 않는다.
    구 계약은 auto_fold 전량을 merged_blocked로 되돌렸고 근거는 "배치 무결성"이었으나
    성립하지 않는다: 이 게이트는 항목마다 독립적으로 quote ⊂ 원문을 검사하므로 무엇이
    검증됐는지 이미 정확히 안다. 검증된 것을 지어낸 것 때문에 함께 막으면 안전은 그대로고
    병목만 생긴다(실측: quote 1건 때문에 한 앱의 배치 전체가 정지했다). 격리분은 여전히
    정본에 못 들어간다 — 지어냄 차단은 유지. align errors(제안 집합 자체가 깨짐)는 성격이
    달라 fold_plan의 fail-closed를 그대로 둔다.
    이미 new/ambiguous로 큐에 있던 rejected sid는 판정 맥락을 잃지 않도록 was를 덮어쓰지
    않고 quote_gate_failed 플래그만 덧붙인다.
    반환: (auto_fold, queue, quote_gate_stat)."""
    quote_gate_stat = {"ok": len(gate["ok"]), "rejected": len(gate["rejected"])}
    if not gate["rejected"]:
        return auto_fold, queue, quote_gate_stat
    rejected_sids = {f"{app_scope}#{r['anchor']}" for r in gate["rejected"]}
    moved, kept = [], []
    for m in auto_fold:
        if m["sid"] in rejected_sids:
            moved.append({**m, "was": "quote_gate_failed", "quote_gate_failed": True})
        else:
            kept.append(m)                      # 검증된 것은 통과 — 연좌 없음
    auto_fold = kept
    moved_sids = {m["sid"] for m in moved}
    queue = [{**q, "quote_gate_failed": True}
             if q["sid"] in rejected_sids and q["sid"] not in moved_sids else q
             for q in queue]
    queue = sorted(queue + moved, key=lambda q: q["sid"])
    return auto_fold, queue, quote_gate_stat


def run_fold(base_dir, app_scope, prev_dir=None, stack=None, ext_path=None):
    """align-proposals+subconcepts 로드(prev_dir이 있으면 이전 회차 산출 이월 병합),
    기존 adjudication.yaml에서 판정된 항목
    (disposition 키 있는 것)을 prev_dispositions로 추출 → fold_plan →
    §8 왕복 게이트(subconcept.verify_subconcepts, sections.yaml 있을 때만) 재검증 →
    adjudication.yaml에 queue+carried+auto_fold 카운트 저장. 반환: out.
    ★게이트는 이 I/O 계층에서만 배선 — fold_plan(순수 코어)은 무수정, sections 개념이
    코어에 침투하지 않는다. 재매핑 로직 자체는 apply_quote_gate(순수함수)로 위임."""
    base_dir = Path(base_dir)
    props = yaml.safe_load(open(base_dir / "align-proposals.yaml"))["proposals"]
    subs = yaml.safe_load(open(base_dir / "subconcepts.yaml"))["subconcepts"]
    # 증분 뒷단: 이전 회차 산출 이월(재추출분 우선). 두 축을 함께 이월해야 성립한다 —
    # subconcept만 이월하면 proposal 누락 error로 fail-closed, proposal만 이월하면
    # phantom sid error. 이월 수는 stats.carried_inputs로 원장에 남긴다(침묵 금지).
    carried_inputs = None
    if prev_dir is not None:
        prev_dir = Path(prev_dir)
        prev_subs = yaml.safe_load(open(prev_dir / "subconcepts.yaml"))["subconcepts"]
        prev_props = yaml.safe_load(open(prev_dir / "align-proposals.yaml"))["proposals"]
        n_new_subs, n_new_props = len(subs), len(props)
        # 대체 판정: extract-manifest의 to_extract(재추출 섹션)에서 온 이전 개념은 이월하지
        sec_path, man_path = base_dir / "sections.yaml", base_dir / "extract-manifest.yaml"
        secs = changed = None
        if sec_path.exists() and man_path.exists():
            secs = yaml.safe_load(open(sec_path))["sections"]
            changed = set((yaml.safe_load(open(man_path)) or {}).get("to_extract") or [])
        new_anchors = {s["anchor"] for s in subs}
        overlap = len({s["anchor"] for s in prev_subs} & new_anchors)   # 같은 anchor 갱신
        subs = merge_carried_subconcepts(subs, prev_subs, sections=secs,
                                         changed_anchors=changed)
        props = merge_carried_proposals(props, prev_props, subs, app_scope)
        n_carried = len(subs) - n_new_subs
        carried_inputs = {"subconcepts": n_carried,
                          "proposals": len(props) - n_new_props,
                          "superseded": len(prev_subs) - n_carried - overlap}
    # 삭제 경로 — 섹션이 사라진 개념은 살아있는 명단에서 빼고 tombstone으로 접는다.
    # 안 빼면 왕복 게이트가 정당한 삭제를 지어냄으로 오인해 배치 전체를 막는다.
    # 증거(removed-sections.yaml)가 있을 때만 동작한다.
    tombstones = []
    rm_path = base_dir / "removed-sections.yaml"
    sec_path_all = base_dir / "sections.yaml"
    if rm_path.exists() and sec_path_all.exists():
        rm_doc = yaml.safe_load(open(rm_path)) or {}
        if rm_doc.get("sections"):
            all_secs = yaml.safe_load(open(sec_path_all))["sections"]
            subs, tombs = split_removed_subconcepts(
                subs, all_secs, rm_doc["sections"], at=rm_doc.get("at"))
            live_sids = {f"{app_scope}#{s['anchor']}" for s in subs}
            props = [p for p in props if p["sid"] in live_sids]
            tombstones = [{"sid": f"{app_scope}#{t['anchor']}", "name": t.get("name"),
                           "quote": t.get("quote"), "removed_at": t.get("removed_at"),
                           "removed_from": t.get("removed_from")} for t in tombs]
    # ★한계: idx를 proposals에서 역산 — phantom sid·누락·중복은 잡지만 "지어낸 target"은
    # 자기참조라 못 잡는다(align 게이트 ① 무력). 진짜 anti-fabrication은 --snap
    # concepts.yaml 앵커 검증으로 후속(plan.md 범위 밖 참조).
    ctx_path, full_path = base_dir / "canon-context.yaml", base_dir / "canon-full.yaml"
    if ctx_path.exists():
        idx = {c["anchor"] for c in (yaml.safe_load(open(ctx_path)) or {}).get("canon") or []}
    else:
        idx = {p["target"] for p in props if p["target"] not in ("NEW", "AMBIGUOUS")}
    full_idx = set((yaml.safe_load(open(full_path)) or {}).get("anchors") or []) \
        if full_path.exists() else None
    adj_path = base_dir / "adjudication.yaml"
    prior_items = []

    def _load_prior(p):
        doc = yaml.safe_load(open(p)) or {}
        return (doc.get("queue") or []) + (doc.get("carried") or [])

    if adj_path.exists():
        prior_items = _load_prior(adj_path)
    # 이전 회차 디렉토리에서는 **판정 완료분만** 이월한다.
    # 미판정 큐까지 끌어오면 대체된 개념이 큐에 되살아난다.
    carried_from_prev = []
    if prev_dir is not None and (Path(prev_dir) / "adjudication.yaml").exists():
        carried_from_prev = [i for i in _load_prior(Path(prev_dir) / "adjudication.yaml")
                             if "disposition" in i]
    prev_dispositions = {item["sid"]: item for item in carried_from_prev}
    prev_dispositions.update({item["sid"]: item for item in prior_items
                              if "disposition" in item})   # 현 회차 원장이 우선
    # 깊은층 anchor 집합 — 조항 병합과 개념 재관측을 가르는 유일한 근거(fold_plan §deep_index).
    deep_idx = ({c["anchor"] for c in (stack.get("concepts") or [])}
                if stack is not None else None)
    out = fold_plan(app_scope, props, subs, idx, prev_dispositions=prev_dispositions,
                    full_index=full_idx, deep_index=deep_idx)
    # 미판정 prior(disposition 없음, 재제안 안 됨)는 판정 이력이 아니라 여전히 판정
    # 대기 중 — carried(이력)에 섞지 말고 queue에 잔류시켜 소멸을 막는다.
    current = {p["sid"] for p in props}
    pending_prior = [item for item in prior_items
                     if "disposition" not in item and item["sid"] not in current]
    queue = sorted(out["adjudication_queue"] + pending_prior, key=lambda q: q["sid"])
    auto_fold = out["auto_fold"]

    # §8 왕복 게이트: sections.yaml이 있을 때만 재검증(없으면 조용한 통과가 아니라
    # stats에 명시적으로 skip을 기록 — 계약 §3-1, subconcept.verify_subconcepts 재사용).
    sections_path = base_dir / "sections.yaml"
    if sections_path.exists():
        from subconcept import verify_subconcepts
        sections = yaml.safe_load(open(sections_path))["sections"]
        # 진실 원천 = sections ∪ articles. 조항 전문도 원문이다 — 좁히면
        # 실질 본문이 조항에만 있는 개념이 얄팍한 인용을 고르게 된다(파일럿 실측).
        arts_path = base_dir / "articles.yaml"
        articles = ((yaml.safe_load(open(arts_path)) or {}).get("articles")
                    if arts_path.exists() else None)
        gate = verify_subconcepts(subs, sections, articles=articles)
        auto_fold, queue, quote_gate_stat = apply_quote_gate(app_scope, auto_fold, queue, gate)
    else:
        quote_gate_stat = "skipped(no sections)"

    # 관계 어휘 등록 게이트(설계 §3 P4/D4) — 어휘 증식을 막는 장치가 있었는데 정작
    # 대조가 없어 실사용이 24종으로 벌어졌다. 원장에 상시 기록해 다음부터는 즉시 보인다.
    # 차단이 아니라 보고다: 미등록은 소유자 승격/재매핑 판정 항목이지 배치 실패가 아니다.
    rel_path = base_dir / "relations-canon.yaml"
    if not rel_path.exists():
        vocab_report = _skipped("relations-canon.yaml 없음")
    elif not ext_path:
        vocab_report = _skipped("어휘 선언 경로 미지정(라이브러리 호출)")
    elif not Path(ext_path).exists():
        vocab_report = _skipped(f"어휘 선언 없음: {ext_path}")
    else:
        from relation_canon import validate_vocabulary
        vocab_report = validate_vocabulary(
            (yaml.safe_load(open(rel_path)) or {}).get("relations") or [],
            yaml.safe_load(open(ext_path)) or {})

    yaml.safe_dump({"queue": queue,
                    "carried": out["carried_dispositions"],
                    "tombstones": tombstones,
                    "auto_fold": auto_fold,
                    "synonym_record": out["align"]["synonym_record"],
                    "stats": {"auto_fold": len(auto_fold),
                              "errors": out["align"]["stats"]["errors"],
                              "quote_gate": quote_gate_stat,
                              "relation_vocab": vocab_report,
                              **({"carried_inputs": carried_inputs}
                                 if carried_inputs is not None else {})}},
                    open(adj_path, "w"), allow_unicode=True, sort_keys=False)
    print(f"fold {app_scope}: 자동 {len(auto_fold)}"
          f" · 판정 큐 {len(queue)}"
          f" · 이월 {len(out['carried_dispositions'])}"
          f" · errors {out['align']['stats']['errors']}"
          f" · quote_gate {quote_gate_stat}")
    return out


# ── S4 promote — 판정 완료분(adjudication.yaml) → depth-stack.yaml 편입 ────────
# build_dispositions(순수 변환)·_replace_app_slice(순수 헬퍼)·run_promote(I/O 다리) 3단.


#: 자동 편입에서 제외되는 was — 왕복 게이트/배치 무결성이 깨진 항목.
#: 원문에 없는 말이 정본에 들어가는 것만은 막는다(지어냄 방지). 여기만 사람 몫으로 남는다.
_AUTO_ADOPT_BLOCKED = {"quote_gate_failed", "merged_blocked"}


def _surface(name):
    """`표면형 (설명)` → 표면형. 두 계보의 이름을 같은 규칙으로 정규화한다."""
    return (name or "").split(" (", 1)[0].split("(", 1)[0].strip()


def absorb_legacy_bodies(concepts, legacy_nodes):
    """구 계보(0a0a001)의 조립 본문을 현 정본 개념에 잇는다. 결정론·LLM 0.

    잇는 규칙: 표면형 일치(`concept:Promotion` ↔ `Promotion (프로모션 …)`). term 노드는 리소스
    머리로 부모 개념에 접는다(`term:Promotion.Rules` → `Promotion`) — 현 스키마에 term
    층이 없기 때문이고, 조각의 provenance 키는 그대로라 출처는 잃지 않는다.

    ★이어지지 않는 노드는 버리지 않고 그대로 돌려준다 — 별칭(`파티션`↔`Partition`)·타
    앱 소유(`StoreAdmin`)·소유자 지정 신규 개념(`주문`)이 섞여 있어 사람 판정 사안이다.
    반환: (bodies {anchor: [조각]}, unbridged [{node, surface, fragments}])."""
    idx = {_surface(c.get("name")): c["anchor"] for c in concepts}
    bodies, unbridged = {}, []
    for node in sorted(legacy_nodes):
        body = legacy_nodes[node] or {}
        frags = body.get("fragments") or []
        raw = node.split(":", 1)[1] if ":" in node else node
        head = raw.split(".", 1)[0] if node.startswith("term:") else raw
        anchor = idx.get(_surface(head))
        if anchor is None:
            unbridged.append({"node": node, "surface": _surface(head), "fragments": frags})
            continue
        bodies.setdefault(anchor, {}).update({f["key"]: f for f in frags})   # 키 dedup
    return ({a: [frags[k] for k in sorted(frags)] for a, frags in sorted(bodies.items())},
            unbridged)


# ── S6 낡음 감시 — 정본 두 스냅샷 + 결정층 ─────────────────────────────────
# 배선이지 신설이 아니다: change_layer(국소화)·decision_axis(낡은 권위 인용)는 이미
# 있었으나 죽은 snapshot_pipeline 계보에만 물려 있어 라이브 정본에서 아무도 부르지
# 않았다. 그래서 "결정이 바뀌면 본문이 낡는다"를 현 정본은 감지하지 못했다.

_DECISION_RE = re.compile(r"\b([A-Z][A-Z0-9]*-D-\d+)\b")


def drift_report(old_canon, new_canon, supersedes=None):
    """두 정본 스냅샷을 비교해 낡은 개념과 낡은 권위 인용을 낸다. 결정론·LLM 0.

    stale = 조각이 바뀌거나 늘거나 사라진 개념(그 본문은 다시 읽혀야 한다).
    stale_citations = 이미 대체된 결정을 근거로 든 개념(침식 유형: 낡은 권위 인용).
    """
    from change_layer import diff_fragments

    def flat(canon):
        return [{**f, "concept": a}
                for a, frags in sorted((canon.get("bodies") or {}).items())
                for f in current_fragments(frags)]

    old_f, new_f = flat(old_canon), flat(new_canon)
    key = lambda f: {**f, "concept": f["concept"], "field": f["key"]}
    diff = diff_fragments([key(f) for f in old_f], [key(f) for f in new_f])
    # diff_fragments는 조각이 아니라 (concept, field) **키 튜플**을 돌려준다.
    touched = {k[0] for group in ("changed", "added", "removed")
               for k in diff.get(group, [])}
    cites = []
    for f in new_f:
        for d in _DECISION_RE.findall(f.get("text") or ""):
            sup = (supersedes or {}).get(d)
            if sup:
                cites.append({"anchor": f["concept"], "cites": d, "superseded_by": sup})
    seen, dedup = set(), []
    for c in cites:
        k = (c["anchor"], c["cites"])
        if k not in seen:
            seen.add(k)
            dedup.append(c)
    return {"stale": sorted(touched), "stale_citations": dedup,
            "stats": {g: len(diff.get(g, [])) for g in ("changed", "added", "removed")}}


def run_absorb(stack_path, legacy_path, queue_path):
    """구 계보 본문 흡수 다리 — 스택에 병합 저장 + 미연결 원장 기록. 1회성 마이그레이션.

    기존 조각 뒤에 이어 붙인다(키 dedup) — 게이트 인용을 비롯한 기존 본문은 보존한다."""
    stack_path, legacy_path, queue_path = Path(stack_path), Path(legacy_path), Path(queue_path)
    stack = yaml.safe_load(open(stack_path)) or {}
    legacy = (yaml.safe_load(open(legacy_path)) or {}).get("nodes") or {}
    absorbed, unbridged = absorb_legacy_bodies(stack.get("concepts") or [], legacy)
    bodies = {k: list(v) for k, v in (stack.get("bodies") or {}).items()}
    for anchor, frags in absorbed.items():
        have = {f["key"] for f in bodies.get(anchor, [])}
        bodies[anchor] = bodies.get(anchor, []) + [f for f in frags if f["key"] not in have]
    stack["bodies"] = {k: bodies[k] for k in sorted(bodies)}
    yaml.safe_dump(stack, open(stack_path, "w"), allow_unicode=True, sort_keys=False)
    yaml.safe_dump({"unbridged": unbridged}, open(queue_path, "w"),
                   allow_unicode=True, sort_keys=False)
    n_frag = sum(len(v) for v in absorbed.values())
    print(f"absorb: 개념 {len(absorbed)}에 조각 {n_frag} 병합 · 미연결 {len(unbridged)}"
          f" → {queue_path.name}")
    return {"absorbed": absorbed, "unbridged": unbridged}


# ── 현행 평면 — 개념 하나당 현행 하나, 나머지는 이력 ────────────────────────


def resolve_current(target, events, valid_at, known_at, scope=None):
    """이 개념을 지배하는 결정의 현행 상태. 결정론·LLM 0.

    반환: None(관련 결정 없음) · {"value", "superseded"} · {"open", "candidates", ...}
    """
    from queries import current_authority, open_decisions

    if not any(e.get("target") == target for e in events or []):
        return None
    auth = current_authority(events, target, valid_at, known_at, scope)
    if auth.get("current_state") == "active" and auth.get("current_option"):
        return {"value": auth["current_option"],
                "superseded": sorted(o for o, st in (auth.get("states") or {}).items()
                                     if st == "superseded")}
    for item in open_decisions(events, valid_at, known_at, scope)["open"]:
        if item["target"] == target:
            out = {"open": True, "candidates": item["deferred_options"]}
            if item.get("resume_triggers"):
                out["resume_triggers"] = item["resume_triggers"]
            return out
    return None


def update_current(concept, new_current):
    """현행을 갱신하고 **직전 현행을 이력으로 내린다**. 소실이 아니라 평면 이동이다.

    단조성은 존재에만 걸린다 — 평면에서 이력으로 내려가는 건 위반이 아니다(설계 정정).
    같은 값이면 이력을 늘리지 않는다(재관측은 갱신이지 변경이 아니다).
    """
    prev = concept.get("current")
    if prev == new_current:
        return concept
    out = {**concept, "current": new_current}
    if prev:
        def _val(h):
            return h if isinstance(h, str) else (h or {}).get("value")
        seen = {_val(prev)}
        hist = [prev]
        for h in concept.get("history") or []:
            v = _val(h)
            if v not in seen:
                seen.add(v)
                hist.append(h)
        out["history"] = hist
    return out


def newest_snapshot(records):
    """스냅샷 목록 → {newest, undated}. **기록된 시각**으로 정한다(유도 금지).

    날짜 없는 스냅샷은 **순위에 넣지 않고 보고한다** — 모르는 것을 최신이라 부르지 않는다."""
    dated = [r for r in records or [] if r.get("generated_at")]
    undated = sorted(r["sha"] for r in records or [] if not r.get("generated_at"))
    newest = max(dated, key=lambda r: r["generated_at"])["sha"] if dated else None
    return {"newest": newest, "undated": undated}


def write_integrity(canon_dir_path, concepts, decisions, archive_segments=None):
    """S6-b 침식 감시 — 죽은 참조·모호 참조를 **brief가 읽는 자리**(`canon/integrity.yaml`)에 남긴다."""
    from l1_integrity import dead_ref_report
    rep = dead_ref_report(concepts, decisions, archive_segments=archive_segments)
    out = Path(canon_dir_path) / "integrity.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    yaml.safe_dump({"meta": rep["stats"], "dead": rep["dead"],
                    "ambiguous": rep["ambiguous"], "archived": rep["archived"]},
                   open(out, "w"), allow_unicode=True, sort_keys=False)
    return out


#: propagate 경로는 코퍼스 선언을 못 받는 자리라 전 kind를 본다(넓게 잡아 놓침 방지).
_KINDS_ALL = ("article", "section", "screen_section", "spec_section", "field",
              "state_enum", "gap")

_ARTICLE_DECISION_RE = re.compile(r"\b[A-Z][A-Z0-9]*-D-\d+\b")


def article_decision_refs(articles):
    """`{조항 anchor: 결정 ID}` — 조항 텍스트에 보이는 결정 표기. 결정론·LLM 0.

    조항이 여러 결정을 가리키면 **비워둔다**(기계가 고르지 않는다). 하나일 때만 쓴다."""
    out = {}
    for a in articles or []:
        ids = set()
        for t in a.get("texts") or []:
            ids |= set(_ARTICLE_DECISION_RE.findall(str(t.get("text") or "")))
        if len(ids) == 1:
            out[a["anchor"]] = ids.pop()
    return out


def propagate_governed_by(subconcepts, members, articles, app):
    """조항 경유 전파 — 개념이 물려받은 조항의 근거를 개념도 물려받는다. 반환 {sid: ref}.

    ★왜: 화면정의서 장르는 결정 ID를 안 쓰고 `[INV-NN]` 조항 ID로만 근거를 댄다. 결정
    ID는 그 조항의 `근거` 필드에 산다(`INV-45` → `INV-D-8812`). 개념이 이미 그 조항을
    본문으로 가지면 근거도 따라오는 게 맞다.

    ★**추출기가 직접 쓴 `governed_by`가 언제나 이긴다** — 전파는 빈자리만 채운다.
    문서가 명시한 것이 기계 유도보다 권위가 높다(자동 편입 계약과 동형).
    ★조항들이 서로 다른 결정을 가리키면 **비워둔다** — 기계가 고르면 지어내는 셈이다."""
    by_article = article_decision_refs(articles)
    written = {f"{app}#{sc['anchor']}" for sc in subconcepts or [] if sc.get("governed_by")}
    out = {}
    for sid, ms in (members or {}).items():
        if sid in written:
            continue
        refs = {by_article.get(m.get("unit") or m.get("article")) for m in ms or []}
        refs.discard(None)
        if len(refs) == 1:
            out[sid] = refs.pop()
    return out


def decision_ref_index(events):
    """결정 원장 → `{문서 표기: 정본 target}` 역인덱스. 결정론·LLM 0.

    ★왜(설계 §2-2): 현행 평면은 이벤트 `target`(`PRIME-COMMERCE.SUMMIT.INV.T.INV-D-7318`)과
    대조하는데 그 dotted 문자열은 **문서에 없다.** 추출기에게 쓰게 하면 지어냄 위험이
    크고 왕복 게이트로 검증할 수도 없다(원문에 없는 문자열이라 게이트가 무력하다).
    그래서 계약은 문서 표기(`INV-D-7318`)를 받고 여기서 해소한다 —
    **원장에 없는 ID는 해소되지 않으므로 지어냄이 구조적으로 무력해진다.**"""
    idx = {}
    for e in events or []:
        t = e.get("target")
        if not t:
            continue
        for ref in (e.get("source") or []):
            idx.setdefault(str(ref), t)
        eid = str(e.get("event_id") or "").rsplit(".", 1)[-1]
        if eid:
            idx.setdefault(eid, t)
    for e in events or []:
        t = e.get("target")
        if t:
            idx[str(t).rsplit(".", 1)[-1]] = t          # 지점 표기가 최종 승자
    return idx


def resolve_decision_ref(ref, index):
    """문서 표기 또는 정본 target → 정본 target. 못 찾으면 None(지어내지 않는다)."""
    if not ref:
        return None
    if ref in set(index.values()):
        return ref                      # 이미 정본 표기(구 원장 호환)
    return index.get(ref)


def _skipped(reason):
    """게이트가 조건 불충족으로 안 돌았다는 기록. **없는 키로 두지 않는다.**"""
    return {"skipped": reason}


def freshness_report(canon_sha, available, newest, layers=None, undated=None):
    """정본이 최신 스냅샷을 보고 있는가. 결정론·I/O 없음.

    layers={층이름: sha} — 정본과 다른 시점을 보는 층은 그 자체가 경고다.
    canon_sha가 없으면 fresh가 아니다(모르는 것을 최신이라 부르지 않는다)."""
    stale_layers = sorted(k for k, v in (layers or {}).items() if v != canon_sha)
    undated = sorted(undated or [])
    fresh = bool(canon_sha) and canon_sha == newest and not stale_layers and not undated
    return {"fresh": fresh, "canon_sha": canon_sha, "newest": newest,
            "available": sorted(available or []), "stale_layers": stale_layers,
            "undated": undated}


def _frag_sort_key(key):
    """조각 정렬 — 게이트 인용(quote)이 항상 먼저, 그다음 조항 조각을 키 순으로.
    한 곳에서만 정한다(정렬이 갈리면 같은 내용에도 diff가 떠 멱등이 깨진다)."""
    return (0, "") if key == "quote" else (1, key)


def supersede_reasons(events):
    """(¬) 층 — `{조항 anchor: 대체한 결정 ID}`. 결정론·LLM 0.

    원장에 세 고리가 이미 다 있다: supersede 이벤트(무엇이 무엇을 대체했나) ·
    `articles`(그 결정이 어느 조항에 반영됐나) · `governed_by`(개념↔결정). 아무도 잇지
    않고 있었을 뿐이다. 대체 결정이 건드린 조항의 조각이 바뀌면 그 결정을 '왜'로 단다.
    추정이 아니라 원장 인용이므로 틀리면 원장이 틀린 것이다."""
    out = {}
    for e in events or []:
        if e.get("type") != "supersede":
            continue
        ref = (e.get("source") or [None])[0] or str(e.get("target") or "").rsplit(".", 1)[-1]
        for art in e.get("articles") or []:
            out.setdefault(art, ref)
    return out


def retire_slice(stack_path, app, archive_dir, at, reason, work_dir=None):
    """앱 슬라이스를 정본에서 빼서 `ledger/legacy/`로 옮긴다. 반환: 아카이브 경로.

    ★불변식 1은 "정본에서 개념이 빠지는 유일한 경로는 tombstone"이다. 은퇴는 그 예외라
    **조용히 지우면 안 된다** — 슬라이스 전량(개념·본문·관계·보류)을 보존하고, 정본 meta에
    무엇을 언제 왜 뺐는지 남긴다. 되돌릴 수 있어야 실험이 실험이다.

    tombstone과 다른 사건이다: tombstone은 "원본에서 사라졌다"(관측), 은퇴는 "이 슬라이스를
    새 파이프라인으로 다시 만들겠다"(운영 결정). 섞으면 원본이 사라진 것처럼 보인다."""
    stack_path = Path(stack_path)
    doc = yaml.safe_load(open(stack_path)) or {}
    prefix = f"{app}#"

    def _mine(sid):
        return str(sid).startswith(prefix)

    concepts = doc.get("concepts") or []
    taken = [c for c in concepts if _mine(c.get("anchor"))]
    if not taken:
        return None                       # 없는 앱을 은퇴시켜도 정본은 안 건드린다
    rels = doc.get("relations") or []
    bodies = doc.get("bodies") or {}
    held = doc.get("held") or {}
    arch = {
        "meta": {"retired_app": app, "retired_at": at, "reason": reason,
                 "generator": "structure_app.retire_slice"},
        "concepts": taken,
        "relations": [r for r in rels if _mine(r.get("from")) or _mine(r.get("to"))],
        "bodies": {k: v for k, v in bodies.items() if _mine(k)},
        "held": {k: [h for h in (v or []) if _mine(h.get("sid"))] for k, v in held.items()},
    }
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    out = archive_dir / f"retired-{app}-{at}.yaml"
    yaml.safe_dump(arch, open(out, "w"), allow_unicode=True, sort_keys=False)

    doc["concepts"] = [c for c in concepts if not _mine(c.get("anchor"))]
    doc["relations"] = [r for r in rels
                        if not (_mine(r.get("from")) or _mine(r.get("to")))]
    doc["bodies"] = {k: v for k, v in bodies.items() if not _mine(k)}
    doc["held"] = {k: [h for h in (v or []) if not _mine(h.get("sid"))]
                   for k, v in held.items()}
    meta = dict(doc.get("meta") or {})
    # 정본만 봐도 "뭔가 빠졌다"가 보여야 한다 — 조용한 감소는 불변식 9와 충돌한다.
    # 은퇴 기록은 뺀 양을 **전부** 담는다 — 게이트가 지표별로 면제를 계산한다.
    meta["retired"] = list(meta.get("retired") or []) + [
        {"app": app, "at": at, "reason": reason,
         "concepts": len(taken),
         "bodies": len(arch["bodies"]),
         "body_chars": sum(len(str(f.get("text") or "")) for v in arch["bodies"].values()
                           for f in v
                           if not f.get("removed_at") and not f.get("superseded_at")),
         "relations": len(arch["relations"]),
         "scopes": len({c.get("scope") for c in taken}),
         "current_filled": sum(1 for c in taken if c.get("current")),
         "archive": out.name}]
    meta["promoted_total"] = len(doc["concepts"])
    doc["meta"] = meta
    yaml.safe_dump(doc, open(stack_path, "w"), allow_unicode=True, sort_keys=False)
    # ★원장까지 옮긴다(삭제 아님) — 아니면 재생 스윕이 그 원장을 읽어 되살린다.
    if work_dir is not None and Path(work_dir).exists():
        import shutil
        dest = archive_dir / f"retired-{app}-{at}"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(work_dir), str(dest))
    return out


def current_fragments(frags):
    """평면에 사는 조각만 — 삭제 표시(`removed_at`)도 대체 표시(`superseded_at`)도 없는 것.

    소유자 모델: "a5인 현재만 보고 안 바뀐 b만 보면 된다." 이력은 지우지 않되 평면에서
    빠지므로, 읽어야 할 양이 전체 조각 수가 아니라 **현행 조각 수**에 비례한다."""
    return [f for f in frags or [] if not f.get("removed_at") and not f.get("superseded_at")]


def members_from_canon(bodies, owned=None):
    """정본 조각 key → 단위 귀속 복원. {sid: [{"unit": u}, ...]} · 결정론.

    ★처방은 이미 정본 안에 있다 — **조각의 key가 곧 귀속 기록**이다(`INV-41|fields.근거`).
    이력 조각도 귀속의 증거다(그 단위를 다시 조립해야 현행이 갱신된다). 다만 **삭제 표시된
    조각은 제외** — 다시 조립하면 지운 것이 되살아난다."""
    out = {}
    for sid in sorted(bodies or {}):
        if owned is not None and not owned(sid):
            continue
        units = []
        for f in bodies.get(sid) or []:
            if f.get("removed_at"):
                continue
            key = str(f.get("key") or "")
            if not key or key == "quote":
                continue          # 게이트 인용은 감사 증거지 단위가 아니다
            u = key.split("|", 1)[0]
            if u and u not in units:
                units.append(u)
        if units:
            # `from_canon` — 왕복 게이트 면제를 **보이게** 남긴다(암묵적 우회 금지).
            out[sid] = [{"unit": u, "from_canon": True} for u in units]
    return out


def merge_members(ledger_members, canon_members):
    """원장 ∪ 정본 유래 귀속. **원장 항목이 이긴다** — 인용을 달고 오기 때문.

    정본 유래 항목으로 원장을 덮으면 `quote`가 사라져 §8 왕복 게이트가 죽는다."""
    out = {}
    for sid in sorted(set(ledger_members or {}) | set(canon_members or {})):
        seen, rows = set(), []
        for m in (ledger_members or {}).get(sid) or []:
            u = m.get("unit") or m.get("article")
            if u and u not in seen:
                seen.add(u)
                rows.append(m)
        for m in (canon_members or {}).get(sid) or []:
            u = m.get("unit")
            if u and u not in seen:
                seen.add(u)
                rows.append(m)
        if rows:
            out[sid] = rows
    return out


def fold_fragment_versions(prev_bodies, fresh_bodies, at, why=None, partial=None,
                           observed_units=None, visible_units=None):
    """축 2 — 조각의 현행/이력 평면. 결정론·멱등.

    why={조항 anchor: 결정 ID} — (¬) 층. 있으면 `superseded_by`로 '왜'를 붙이고,
    없으면 비운다(설계 §3-2: '왜'는 필수가 아니다)."""
    why = why or {}
    partial = set(partial or ())
    # ★양쪽 다 옮긴다. fresh도 오염돼 있다 — promote가 prev를 복사해 시작하므로
    # 비소유 sid의 옛 키가 fresh에 실려 온다. prev만 정규화하면 옛 키가 **신규 조각**
    # 불변식 16 — 루트 이동은 삭제가 아니다. 양쪽 다 정규화한다(fresh도 옛 키를 물고 온다).
    prev_bodies = realign_bodies(prev_bodies, fresh_bodies, visible_units)
    fresh_bodies = realign_bodies(fresh_bodies, fresh_bodies, visible_units)
    out = {}
    for anchor in sorted(set(prev_bodies) | set(fresh_bodies)):
        now = {f["key"]: f for f in fresh_bodies.get(anchor, [])}
        is_partial = anchor in partial
        seen_units = (observed_units or {}).get(anchor)
        live, history = {}, []
        _hist_seen = set()                             # 같은 사건은 한 번만
        def _push_hist(f):
            # ★이력 멱등 — (key, text, superseded_at)이 같으면 같은 사건이다. 재생
            k = (f.get("key"), f.get("text"), f.get("superseded_at"))
            if k not in _hist_seen:
                _hist_seen.add(k)
                history.append(f)
        for f in prev_bodies.get(anchor, []):
            if f.get("superseded_at"):
                _push_hist(f)                          # 이미 이력 — 보존하되 중복은 접는다
                continue
            key = f["key"]
            if key == "quote":
                # 게이트 인용은 조항 파생이 아니라 **감사 증거**다 — 조항이 사라져서 죽는
                # 종류가 아니다. 축 2에서 "quote는 버전 축에 안 태운다"를 세웠는데
                live[key] = {k: v for k, v in (now.get(key) or f).items() if k != "removed_at"} \
                    if (now.get(key) or {}).get("text") or not now.get(key) else f
                live[key] = {k: v for k, v in live[key].items() if k != "removed_at"}
                continue
            if key not in now:
                _unit = key.split("|", 1)[0]
                if visible_units is not None and _unit in visible_units:
                    live[key] = f              # 단위가 코퍼스에 실재 — 판정 유보
                    continue
                _unit_seen = seen_units is not None and _unit in seen_units
                if is_partial and not _unit_seen:
                    live[key] = f              # 이번에 안 실렸을 뿐 — 죽었다고 하지 않는다
                else:
                    live[key] = {**f, "removed_at": f.get("removed_at") or at}
                continue
            if key == "quote" or now[key].get("text") == f.get("text"):
                # 게이트 인용은 **감사 증거**지 본문이 아니다 — 버전 축에 안 태운다.
                pick = now[key] if (key == "quote" and now[key].get("text")) else f
                live[key] = {k: v for k, v in pick.items() if k != "removed_at"}
            else:
                aged = {**f, "superseded_at": at}
                reason = why.get(str(key).split("|", 1)[0])
                if reason:
                    aged["superseded_by"] = reason
                _push_hist(aged)
                live[key] = now[key]                   # ★새 텍스트가 현행이 된다
        for key, f in now.items():
            live.setdefault(key, f)
        ordered = [live[k] for k in sorted(live, key=_frag_sort_key)]
        history.sort(key=lambda f: (_frag_sort_key(f["key"]), f.get("superseded_at") or "",
                                    f.get("text") or ""))
        out[anchor] = ordered + history
    return out


def tombstone_lost_fragments(prev_bodies, fresh_bodies, at):
    """이번 조립에서 못 만든 조각을 지우지 않고 삭제 표시한다. 결정론."""
    prev_bodies = realign_bodies(prev_bodies, fresh_bodies)   # 불변식 16
    out = {}
    for anchor in sorted(set(prev_bodies) | set(fresh_bodies)):
        now = {f["key"]: f for f in fresh_bodies.get(anchor, [])}
        merged = {}
        for f in prev_bodies.get(anchor, []):
            if f["key"] in now:
                merged[f["key"]] = {k: v for k, v in f.items() if k != "removed_at"}
            else:
                merged[f["key"]] = {**f, "removed_at": f.get("removed_at") or at}
        for k, f in now.items():
            merged.setdefault(k, f)
        out[anchor] = [merged[k] for k in sorted(merged, key=_frag_sort_key)]
    return out


def apply_aliases(concepts, aliases):
    """S3c — 별칭을 **비파괴로** 단다. 개념을 합치지 않는다."""
    by_anchor = {}
    for a in aliases or []:
        by_anchor.setdefault(a.get("anchor"), []).append(a)
    out = []
    for c in concepts:
        add = by_anchor.get(c["anchor"])
        if not add:
            out.append(c)
            continue
        have = {x.get("surface") for x in (c.get("aliases") or [])}
        fresh = [{"surface": a["surface"], "basis": a.get("basis", "tier_b"),
                  "confidence": a.get("confidence"), "needs_review": True}
                 for a in sorted(add, key=lambda a: a["surface"])
                 if a.get("surface") and a["surface"] not in have]
        out.append({**c, "aliases": fresh + list(c.get("aliases") or [])})
    return out


def check_snapshot_order(requested, canon_sha, snapshot_index):
    """불변식 11 — 정본을 **자기보다 오래된 스냅샷으로** 재생하지 않는다.

    ★모르면 막지 않는다 — 시각 없는 스냅샷·미등록 SHA·첫 회차(canon_sha 없음)는 통과.
    모르는 것을 위반이라 부르면 사람이 게이트를 끄기 시작한다.
    롤백은 정당한 작업이라 금지가 아니라 **명시**를 요구한다(CLI `--allow-older`)."""
    at = {r.get("sha"): r.get("generated_at") for r in (snapshot_index or [])}
    req_at, canon_at = at.get(requested), at.get(canon_sha)
    out = {"requested": requested, "canon": canon_sha,
           "requested_at": req_at, "canon_at": canon_at}
    out["ok"] = not (canon_sha and req_at and canon_at and req_at < canon_at)
    return out


def rekey_members_to_canon(members, auto_fold):
    """병합된 하위개념의 귀속을 **정본 개념 anchor로 옮긴다**. 결정론·LLM 0."""
    remap = {x["sid"]: x["target"] for x in (auto_fold or [])
             if x.get("target") and x.get("sid") and x["target"] != x["sid"]}
    if not remap:
        return dict(members or {})
    out = {}
    for sid in sorted(members or {}):
        key = remap.get(sid, sid)
        bucket = out.setdefault(key, [])
        have = {(m.get("unit") or m.get("article"), m.get("quote")) for m in bucket}
        for m in members[sid]:
            k = (m.get("unit") or m.get("article"), m.get("quote"))
            if k not in have:
                have.add(k)
                bucket.append(m)
    return out


def rekey_bodies_to_canon(bodies, auto_fold):
    """정본에 **이미 쌓인** 조각을 병합 대상 개념으로 옮긴다. 결정론·LLM 0.

    옮기는 지점을 `prev_bodies` 한 곳으로 잡는 이유가 그것이다 — 여기서 옮기면 뒤따르는
    `members_from_canon`이 자동으로 옳은 키를 내므로 고칠 자리가 둘이 아니라 하나다.

    조각이 겹치면 **먼저 온 것(=병합 대상 자신의 것)이 이긴다.** 실제로 겹치는
    유일한 자리는 `quote`인데, 그건 정본 개념 자신의 게이트 증거라 병합된 쪽 인용이
    덮으면 감사 흔적이 바뀐다."""
    remap = {x["sid"]: x["target"] for x in (auto_fold or [])
             if x.get("target") and x.get("sid") and x["target"] != x["sid"]}
    if not remap:
        return dict(bodies or {})
    _ident = lambda f: (f.get("key"), f.get("superseded_at"))
    out = {}
    for sid in sorted(bodies or {}, key=lambda s: (s in remap, s)):
        key = remap.get(sid, sid)
        bucket = out.setdefault(key, [])
        have = {_ident(f) for f in bucket}
        for f in bodies[sid]:
            if _ident(f) not in have:
                have.add(_ident(f))
                bucket.append(f)
    return {k: out[k] for k in sorted(out)}


def stranded_bodies(concepts, bodies):
    """**모든 본문 키는 실재하는 개념을 가리키는가** — 불변식 10."""
    anchors = {c["anchor"] for c in concepts or []}
    return sorted(k for k in (bodies or {}) if k not in anchors)


def assemble_body_fragments(rows, tier_a, members=None):
    """A 조립층 — 승격 행의 조항 target을 원문 조각으로 펼친다. 결정론·LLM 0.

    조각 키는 `<조항anchor>|<필드>` — 어느 조항의 어느 자리에서 왔는지 보존한다(조항이
    사라져도 지식은 남되, 출처는 잃지 않는다). 해소 안 되는 target은 조각을 만들지 않는다."""
    from body_probe import _texts_of
    by_anchor = {c["anchor"]: c for c in tier_a}
    members = members or {}

    def _expand(article_anchor):
        """조항 하나를 조각들로. 없는 조항은 조각을 만들지 않는다(지어냄 0)."""
        art = by_anchor.get(article_anchor)
        if art is None:
            return []
        return [{"key": f"{article_anchor}|{k}", "text": t} for k, t in _texts_of(art) if t]

    def _gate(article_anchor, quote):
        """왕복 게이트 — quote가 그 조항 원문에 실재해야 귀속을 인정한다."""
        art = by_anchor.get(article_anchor)
        if art is None or not quote:
            return False
        return any(quote in t for _, t in _texts_of(art) if t)

    out = {}
    for row in sorted(rows, key=lambda r: r["sid"]):
        arts = set()
        if row.get("target") in by_anchor:
            arts.add(row["target"])                       # 정렬된 조항(S2 산출)
        for m in members.get(row["sid"], []):             # 서술 단위 귀속(S3a 원장)
            # `unit`이 새 이름, `article`은 기존 원장 호환 — 이름을 바꾸면서 옛 원장을
            # 못 읽게 만드는 게 이 프로젝트가 반복해서 당한 사고다(fixture 재편 전례).
            u = m.get("unit") or m.get("article")
            # ★정본 유래 귀속은 **새 주장이 아니라 기록된 사실**이라 게이트를 면제한다
            if m.get("from_canon") or _gate(u, m.get("quote")):
                arts.add(u)
        frags = {}
        for a in sorted(arts):
            for f in _expand(a):
                frags.setdefault(f["key"], f)
        if frags:
            out[row["sid"]] = [frags[k] for k in sorted(frags)]
    return out


def build_dispositions(saved_adjudication, subconcepts, app, auto_adopt=False,
                       absorbed=None):
    """S4 promote 다리 — 저장된 adjudication.yaml(queue+carried)을 depth_promote.fold_depth
    스키마 행으로 변환. name은 저장 항목에 없으면 subconcepts(anchor)에서 조회.
    결정론(sid 정렬). 게이트 실패 이력은 감사 흔적으로 전파 — 소유자 판정이 override지만
    흔적 소실 금지(quote_gate_failed 플래그는 override돼도 행에 그대로 실린다)."""
    sc_by_anchor = {s["anchor"]: s for s in subconcepts}
    absorbed = absorbed or set()
    items = [i for i in ((saved_adjudication.get("queue") or [])
                         + (saved_adjudication.get("carried") or []))
             if i.get("sid") not in absorbed]
    rows = []
    # tombstone은 판정 대상이 아니라 관측 사실(섹션이 사라졌다)이라 auto_adopt와 무관하게
    # 항상 편입된다 — 표시를 미루면 그동안 정본이 유령을 들고 있게 된다.
    for t in (saved_adjudication.get("tombstones") or []):
        rows.append({"sid": t["sid"], "app": app, "name": t.get("name"),
                     "was": "removed", "disposition": "tombstone",
                     "removed_at": t.get("removed_at"), "quote": t.get("quote")})
    for item in items:
        auto = False
        if "disposition" not in item:
            if not auto_adopt or item.get("was") in _AUTO_ADOPT_BLOCKED \
                    or item.get("quote_gate_failed"):
                continue
            auto = True
        sid = item["sid"]
        anc = sid.split("#", 1)[1]
        row = {"sid": sid, "app": app,
               # target(조항)은 판정 맥락이자 **본문 조립의 유일한 출처 단서**다 —
               # 여기서 떨어뜨리면 assemble_body_fragments가 펼칠 조항을 잃는다.
               "target": item.get("target"),
               "name": item.get("name") or sc_by_anchor.get(anc, {}).get("name"),
               "was": item.get("was"),
               "disposition": "auto_adopt" if auto else item["disposition"]}
        if "align_to" in item:
            row["align_to"] = item["align_to"]
        if item.get("quote_gate_failed"):
            row["quote_gate_failed"] = True
        if auto and item.get("was") == "ambiguous":
            row["needs_review"] = True      # 편입하되 사후 리뷰 — 막지는 않는다
        rows.append(row)
    rows.sort(key=lambda r: r["sid"])
    return rows


def stamp_last_seen(stack_concepts, auto_fold, snap):
    """★P1-c 재관측=갱신 — auto_fold가 겨냥한 정본 노드에 `last_seen`(스냅샷 SHA)을 찍는다.
    반환: (갱신된 concepts, 갱신 건수). 결정론(입력 순서 보존, 새 노드 0).

    남겨야 하는 이유는 **tombstone의 짝**이기 때문이다: 삭제는 섹션이 통째로 사라질 때만
    잡히고(split_removed_subconcepts), 섹션은 남았는데 그 개념 서술만 빠진 경우는 못 잡는다.
    last_seen이 있으면 "몇 회차째 안 보이는 개념"이 tombstone 후보로 드러난다.

    ★새 노드가 안 생기는 게 정상이다 — 그게 재제안이 사라졌다는 증거다."""
    targets = {m.get("target") for m in auto_fold or []}
    out, n = [], 0
    for c in stack_concepts:
        if c["anchor"] in targets:
            out.append({**c, "last_seen": snap})
            n += 1
        else:
            out.append(c)                 # 이번에 안 보인 것은 그대로 — 노후 신호 보존
    return out, n


def _replace_app_slice(prev, new, matches, sort_key):
    """이 앱 소유분(matches로 판별)을 prev에서 제거하고 new로 교체 후 정렬.
    concepts/relations/held 3버킷 공용(bodies는 dict라 별도 처리)."""
    kept = [x for x in prev if not matches(x)]
    kept += new
    kept.sort(key=sort_key)
    return kept


def absorb_resolved_new(relations):
    """같은 (from,to) 쌍에 판정된 어휘가 있으면 `NEW` 표식을 접는다. 결정론."""
    judged = {(r.get("from"), r.get("to")) for r in relations or []
              if r.get("canonical") and r.get("canonical") != "NEW"}
    return [r for r in relations or []
            if r.get("canonical") != "NEW" or (r.get("from"), r.get("to")) not in judged]


def anchor_uniqueness_report(concepts):
    """불변식 8 — 정본에 같은 anchor가 두 번 나오지 않는다. 반환 {ok, duplicates}."""
    seen = {}
    for c in concepts or []:
        a = c.get("anchor")
        seen[a] = seen.get(a, 0) + 1
    dups = [{"anchor": a, "count": n} for a, n in sorted(seen.items()) if n > 1]
    return {"ok": not dups, "duplicates": dups}


def doc_identity_report(bodies):
    """불변식 16 — 한 문서가 정본 안에서 두 신원으로 갈려 있지 않다. {ok, split}.

    갈림의 정의는 **경로 접미 관계**다(`reference/x` ⊂ `planning/reference/x`).
    같은 basename이어도 접미 관계가 아니면 진짜 형제 문서다(`backlog/guest-request` vs
    `작업완료/guest-request`) — 안 잡는다."""
    from doc_identity import split_fragment_key, same_document
    slugs = sorted({d for fs in (bodies or {}).values() for f in (fs or [])
                    for d in (split_fragment_key(f.get("key"))[0],) if d})
    groups = {}
    for i, a in enumerate(slugs):
        for b in slugs[i + 1:]:
            if same_document(a, b):
                key = canonical_doc_name(a)
                groups.setdefault(key, set()).update((a, b))
    split = [{"identity": k, "slugs": sorted(v)} for k, v in sorted(groups.items())]
    return {"ok": not split, "split": split}


def canonical_doc_name(doc_slug):
    from doc_identity import canonical_doc
    return canonical_doc(doc_slug)


# 회귀를 잡는 축. `aggregation_rate`도 든다 — 지표만 찍고 회귀를 안 잡으면 소용없다.
_METRIC_KEYS = ("concepts", "relations", "bodies", "body_chars_unique", "current_filled",
                "scopes", "aggregation_rate")
# 초록 → 빨강 전이를 회귀로 잡는 불리언 축(anchor_unique와 같은 층).
_BOOL_GATE_KEYS = ("anchor_unique", "doc_identity_unique")


def _ingested_docs(doc):
    """정본이 **실제로 읽은** 문서 신원 집합 — 조각 키의 문서 축에서 관측 유도.
    선언이 아니라 관측이라 registry가 바뀌어도 따라온다(지어냄 0)."""
    from doc_identity import split_fragment_key
    return {d for fs in (doc.get("bodies") or {}).values() for f in (fs or [])
            for d in (split_fragment_key(f.get("key"))[0],) if d}


def unresolved_frozen_report(concepts, bodies, archive_segments, ingested_docs=None):
    """불변식 12 — **반증 문서를 안 읽은 주장이 확정 사실 자리에 앉지 않는다**. {ok, offenders}"""
    from archive_closure import archive_reference_report
    flagged = {x["anchor"] for x in archive_reference_report(
        bodies, archive_segments, ingested_docs)["unresolved"]}
    offenders = sorted(c["anchor"] for c in (concepts or [])
                       if c.get("anchor") in flagged
                       and c.get("commitment") == "frozen" and c.get("confidence") == "high")
    return {"ok": not offenders, "offenders": offenders}


def canon_metrics(doc, archive_segments=(), ingested_docs=None):
    """정본 자체를 재는 지표 — `canon/metrics.yaml`의 내용(결정론·LLM 0)."""
    concepts = doc.get("concepts") or []
    bodies = doc.get("bodies") or {}
    live_chars = tomb = aged = 0
    unique_texts = set()
    for anchor, frags in bodies.items():
        for f in frags if isinstance(frags, list) else []:
            text = str((f or {}).get("text") or "")
            if (f or {}).get("removed_at"):
                tomb += 1                  # 출처가 사라진 조각
            elif (f or {}).get("superseded_at"):
                aged += 1                  # 갱신돼 이력으로 내려간 조각
            else:
                live_chars += len(text)    # ★현행 평면만 센다(이력을 세면 시금석이 거짓말)
                unique_texts.add((anchor, text))
    mult = {"none": 0, "one": 0, "multi": 0}
    for c in concepts:
        keys = bodies.get(c.get("anchor")) or []
        units = {str(f.get("key")).split("|")[0]
                 for f in keys if isinstance(f, dict) and "|" in str(f.get("key") or "")}
        mult["none" if not units else ("one" if len(units) == 1 else "multi")] += 1
    n = len(concepts)
    mult["aggregation_rate"] = round(mult["multi"] / n, 4) if n else 0.0
    held = doc.get("held") or {}
    return {"concepts": len(concepts),
            "unit_multiplicity": mult,
            "aggregation_rate": mult["aggregation_rate"],
            "relations": len(doc.get("relations") or []),
            "bodies": len(bodies),
            "body_chars": live_chars,
            "body_chars_unique": sum(len(t) for _, t in unique_texts),
            "tombstoned_fragments": tomb,
            "history_fragments": aged,
            "current_filled": sum(1 for c in concepts if c.get("current")),
            "nameless": sum(1 for c in concepts if not c.get("name")),
            "scopes": len({c.get("scope") for c in concepts}),
            "anchor_unique": anchor_uniqueness_report(concepts)["ok"],
            "doc_identity_unique": doc_identity_report(bodies)["ok"],
            "unresolved_frozen": len(unresolved_frozen_report(
                concepts, bodies, archive_segments, ingested_docs)["offenders"]),
            "held_total": {k: len(v or []) for k, v in held.items()},
            "dangling_auto_fold": len((doc.get("meta") or {}).get("dangling_auto_fold") or []),
            "source_sha": (doc.get("meta") or {}).get("source_sha")}


#: 실행 순서에 따라 바뀌는 메타 — 내용이 같으면 재현된 것이다.
_VOLATILE_META = ("last_promoted_app",)


def _content_key(doc):
    """내용 동일성 판정용 정규형 — 실행 순서에만 달린 메타는 뺀다(재현성 판정과 같은 기준)."""
    meta = {k: v for k, v in (doc.get("meta") or {}).items() if k not in _VOLATILE_META}
    return yaml.safe_dump({**{k: v for k, v in doc.items() if k != "meta"}, "meta": meta},
                          allow_unicode=True, sort_keys=True)


def archive_round(canon_file, rounds_dir):
    """회차 정본을 원장에 남긴다. 반환: 새 파일 경로 · 내용이 그대로면 None.

    ★회차의 정의: **내용이 바뀐 재생만 한 회차다.** 재현성 검사가 매 재생마다 promote를
    한 번 더 돌리므로 실행 횟수로 세면 회차가 뻥튀기된다."""
    canon_file = Path(canon_file)
    rounds_dir = Path(rounds_dir)
    if not canon_file.exists():
        return None
    doc = yaml.safe_load(open(canon_file)) or {}
    prev = previous_round(rounds_dir)
    if prev is not None and _content_key(yaml.safe_load(open(prev)) or {}) == _content_key(doc):
        return None
    rounds_dir.mkdir(parents=True, exist_ok=True)
    n = len(list(rounds_dir.glob("round-*.yaml"))) + 1
    out = rounds_dir / f"round-{n:04d}.yaml"
    out.write_text(canon_file.read_text(encoding="utf-8"), encoding="utf-8")
    return out


def previous_round(rounds_dir):
    """가장 최근 회차 정본. 없으면 None."""
    rounds_dir = Path(rounds_dir)
    files = sorted(rounds_dir.glob("round-*.yaml")) if rounds_dir.exists() else []
    return files[-1] if files else None


def reproducibility_report(a, b):
    """불변식 4 — 같은 입력을 다시 접으면 같은 산출인가. 결정론·I/O 없음.

    ★감사에서 드러난 것: 불변식 9종 중 **4번만 자동 검사가 없었다.** 규약으로 두고 매
    회차 사람이 손으로 확인했다 — 게이트인 척했을 뿐이다. "코드 게이트가 산출물을 안
    잰다"를 고쳐놓고 정작 재현성은 아무도 안 재고 있었다.

    다른 점은 **지표 이름으로** 말한다(YAML diff는 사람이 못 읽는다). 실행 순서에만
    달린 메타는 무시한다 — 앱 순서만 바꿔도 값이 달라지는 자리라 내용 동일성과 무관하다."""
    ma, mb = canon_metrics(a), canon_metrics(b)
    diffs = [{"metric": k, "first": ma.get(k), "again": mb.get(k)}
             for k in sorted(set(ma) | set(mb)) if ma.get(k) != mb.get(k)]

    def _clean(doc):
        meta = {k: v for k, v in (doc.get("meta") or {}).items() if k not in _VOLATILE_META}
        return {**{k: v for k, v in doc.items() if k != "meta"}, "meta": meta}

    same_bytes = yaml.safe_dump(_clean(a), allow_unicode=True, sort_keys=True) == \
        yaml.safe_dump(_clean(b), allow_unicode=True, sort_keys=True)
    return {"ok": not diffs and same_bytes, "diffs": diffs,
            "byte_identical": same_bytes}


def metrics_gate(prev, cur, retired=None):
    """불변식 9 — 정본은 회차를 거치며 줄지 않는다. 반환 {ok, regressions}."""
    if not prev:
        return {"ok": True, "regressions": []}
    # ★은퇴로 인한 감소는 위반이 아니다 — 다만 **기록이 있을 때만** 봐준다.
    # 게이트가 정당한 폐기를 매번 위반으로 띄우면 사람이 게이트를 무시하기 시작한다
    # (게이트가 죽는 가장 흔한 경로). 면제는 `meta.retired` 기록에 근거하고,
    # 감소분이 은퇴분을 넘으면 초과분은 여전히 위반이다. 지표마다 자기 은퇴분만 면제된다.
    excused = {}
    for r in retired or []:
        for k, v in (r or {}).items():
            if isinstance(v, int):
                excused[k] = excused.get(k, 0) + v
    regs = [{"metric": k, "was": prev[k], "now": cur.get(k, 0)}
            for k in sorted(_METRIC_KEYS)
            if isinstance(prev.get(k), int)
            and cur.get(k, 0) < prev[k] - excused.get(k, 0)]
    regs += [{"metric": k, "was": True, "now": False} for k in _BOOL_GATE_KEYS
             if prev.get(k) and not cur.get(k)]
    out = {"ok": not regs, "regressions": regs}
    if excused:
        out["retired_total"] = excused.get("concepts", 0)
    return out


def _merge_node(old, new):
    """개념 병합 — **빈 값은 채워진 값을 덮지 않는다.**"""
    out = dict(old)
    for k, v in new.items():
        if v is None or v == "" or v == [] or v == {}:
            continue
        out[k] = v
    return out


def _collapse_duplicate_anchors(concepts):
    """같은 anchor는 같은 개념이다 — 중복을 병합으로 해소한다. 반환 (concepts, 병합건수).
    삭제가 아니라 병합이므로 채워진 필드는 하나도 잃지 않는다(단조성 유지)."""
    by_anchor, order = {}, []
    for c in concepts:
        a = c["anchor"]
        if a in by_anchor:
            by_anchor[a] = _merge_node(by_anchor[a], c)
        else:
            by_anchor[a] = c
            order.append(a)
    return [by_anchor[a] for a in order], len(concepts) - len(order)


def run_promote(base_dir, app, stack_path, app_scope, auto_adopt=True, tier_a=None,
                snap=None, events=None, valid_at="2030-12-31", known_at="2030-12-31"):
    """S4 promote 다리 — probe(subconcepts+relations-canon)+adjudication.yaml(판정 완료분)
    → depth_promote.fold_depth → depth-stack.yaml에 이 앱 단위로 병합(타 앱 항목 보존,
    이 앱 항목은 전량 교체). 결정론·멱등(같은 입력 재실행 diff 0).
    probes는 depth_promote.load_probes(subconcept-<app> 명명 고정)를 재사용하지 않고
    base_dir에서 직접 로드 — tmp 테스트·임의 앱 모두 base_dir 주입으로 일관되게 지원."""
    import depth_promote as dp   # promote 경로만 쓰는 지역 import(l1_integrity·concept_align 관례)
    base_dir = Path(base_dir)
    stack_path = Path(stack_path)
    subs = yaml.safe_load(open(base_dir / "subconcepts.yaml"))["subconcepts"]
    rels = yaml.safe_load(open(base_dir / "relations-canon.yaml"))["relations"]
    adj_doc = yaml.safe_load(open(base_dir / "adjudication.yaml")) or {}
    # Tier B 원장(S3a 귀속·S3c 별칭) — 없으면 없는 대로 간다(첫 회차·미실행 앱).
    def _ledger(name, key):
        p = base_dir / name
        return (yaml.safe_load(open(p)) or {}).get(key) if p.exists() else None
    # ★귀속은 **원장 ∪ 정본 유래**다 — 원장은 회차마다 덮어써지므로 그것만 보면
    # 좁은 증분 회차에서 정본 조각이 조립 대상에서 빠져 화석이 된다.
    members = _ledger("members.yaml", "members") or {}
    aliases = _ledger("aliases.yaml", "aliases") or []
    # 흡수 기록은 정본에 산다(consolidate.apply_consolidation의 absorbed_anchors).
    _absorbed = {a for c in (yaml.safe_load(open(stack_path)) or {}).get("concepts") or []
                 for a in (c.get("absorbed_anchors") or [])} if Path(stack_path).exists() else set()
    rows = build_dispositions(adj_doc, subs, app, auto_adopt=auto_adopt,
                              absorbed=_absorbed)
    probes = {app: {"subconcepts": subs, "relations": rels}}
    stack = yaml.safe_load(open(stack_path)) or {}
    # ★병합된 개념을 관계 끝점으로 풀 지도. 원장이 이미 기록한 것이지
    # 새로 판정하는 게 아니다 — 없으면 종전 동작(같은 sid 접두만 해소).
    out = dp.fold_depth({"dispositions": rows}, probes, app_scopes={app: app_scope},
                        canon_anchors={c["anchor"] for c in (stack.get("concepts") or [])},
                        merged_into=adj_doc.get("synonym_record") or {})
    # ★병합 접두는 CLI 앱 슬러그가 아니라 **원장 sid**에서 온다.
    _prefixes = sorted({r["sid"].split("#", 1)[0] + "#" for r in rows if "#" in r.get("sid", "")})
    _prefixes = _prefixes or [f"{app}#"]

    def _owned(sid):
        return any(str(sid).startswith(p) for p in _prefixes)
    # 스냅샷 SHA — prep이 manifest에 남긴 것(promote가 시점을 따로 알 방법이 없다).
    # 재관측 last_seen·조각 tombstone·정본 최신성 기록이 전부 이 값을 쓴다.
    # 호출자가 준 snap이 우선(수기 probe엔 manifest가 없다). 모르면 None —
    # 모르는 것을 최신이라 부르지 않는다(freshness_report).
    man_path = base_dir / "extract-manifest.yaml"
    snap = snap or ((yaml.safe_load(open(man_path)) or {}).get("snap")
                    if man_path.exists() else None)

    # ★개념은 교체가 아니라 anchor 기준 **병합**이다(루프 닫힘 이후 필수).
    # 2회차에는 이미 정본인 개념을 추출기가 그 anchor로 겨냥한다 → merged → auto_fold.
    # ★누적 필드는 재생성으로 지워지지 않는다. fold_depth는 probe에서 노드를 새로 짓기
    # 때문에, 정본이 회차를 거치며 쌓은 것(현행·이력·별칭)이 그 순간 전부 사라진다 —
    new_by_anchor = {c["anchor"]: c for c in out["concepts"]}
    merged_app = [_merge_node(c, new_by_anchor.pop(c["anchor"]))
                  if c["anchor"] in new_by_anchor else c
                  for c in stack.get("concepts", []) if _owned(c["anchor"])]
    merged_app += [new_by_anchor[a] for a in sorted(new_by_anchor)]
    concepts = sorted([c for c in stack.get("concepts", [])
                       if not _owned(c["anchor"])] + merged_app,
                      key=lambda c: c["anchor"])
    concepts, n_collapsed = _collapse_duplicate_anchors(concepts)

    skipped, unresolved = {}, []
    if not tier_a:
        skipped["body_assembly"] = "tier_a 스냅샷 미지정 — 조항 원문이 없어 본문 조각 0"
        skipped["fragment_tombstone"] = "tier_a 스냅샷 미지정"
    if not snap:
        skipped["last_seen"] = "snap 미지정(manifest·--snap 둘 다 없음) — 재관측 기록 불가"
    if not events:
        skipped["current_plane"] = "결정층 이벤트 미주입 — 현행/미결 칸 미채움"
    elif not any(sc.get("governed_by") for sc in subs):
        skipped["current_plane"] = "개념에 governed_by 없음(S3a 미실행) — 이벤트는 있으나 걸 데가 없다"

    # ★현행 평면 — 개념이 governed_by로 가리키는 결정의 현행 상태를 한 칸에 채운다.
    # 확정이면 값, 미결이면 미결인 채로(강등 아님). 직전 현행은 이력으로 내려간다.
    if events:
        ref_index = decision_ref_index(events)
        # 조항 경유 전파 — 추출기가 직접 쓴 것이 이기고, 전파는 빈자리만 채운다.
        _via = propagate_governed_by(subs, members, tier_a and statement_units(
            tier_a, app_scope, _KINDS_ALL) or [], app)
        gov, unresolved = {}, []
        for sc in subs:
            ref = sc.get("governed_by")
            if not ref:
                continue
            sid = f"{app}#{sc['anchor']}"
            target = resolve_decision_ref(ref, ref_index)
            if target:
                gov[sid] = target
            else:
                unresolved.append({"sid": sid, "ref": ref})   # 지어낸 건 남되 안 들어간다
        for sid, ref in sorted(_via.items()):
            if sid in gov:
                continue
            target = resolve_decision_ref(ref, ref_index)
            if target:
                gov[sid] = target
        filled = []
        for c in concepts:
            target = gov.get(c["anchor"])
            cur = resolve_current(target, events, valid_at, known_at) if target else None
            filled.append(update_current(c, cur) if cur else c)
        concepts = filled

    # ★S3c 별칭 — 비파괴 부착(개념을 합치지 않는다, 설계 §3).
    if aliases:
        concepts = apply_aliases(concepts, aliases)

    n_seen = 0
    if snap:
        _seen_now = [{"target": c["anchor"]} for c in out["concepts"]]
        concepts, n_seen = stamp_last_seen(
            concepts, (adj_doc.get("auto_fold") or []) + _seen_now, snap)

    _rkey = lambda r: (r["from"], r["to"], str(r.get("canonical")))
    _rel_merged = {_rkey(r): r for r in stack.get("relations", []) if _owned(r["from"]) or _owned(r["to"])}
    # 빈 값은 채워진 값을 덮지 않는다 — 개념(_merge_node)과 같은 원칙. 재관측 회차의
    # 관계는 quote가 비어 올 수 있는데 그게 직전 회차의 근거를 지우면 안 된다.
    for r in out["relations"]:
        k = _rkey(r)
        _rel_merged[k] = _merge_node(_rel_merged[k], r) if k in _rel_merged else r
    relations = sorted(absorb_resolved_new(
        [r for r in stack.get("relations", []) if not (_owned(r["from"]) or _owned(r["to"]))]
        + [_rel_merged[k] for k in sorted(_rel_merged)]), key=_rkey)

    # bodies는 dict라 _replace_app_slice(리스트 전용)를 못 쓴다 — 정렬을 여기서 건다.
    # 정렬 없이 update만 하면 **promote 순서가 곧 파일 순서**가 되어, 내용이 같아도
    # 앱 순서만 바꾸면 diff가 뜬다("같은 입력 재실행 diff 0" 불변식 위반 → 스냅샷 대조
    # 감시층이 전부 오탐).
    # ★본문도 교체가 아니라 anchor 기준 **병합**이다 — 개념(위)과 같은 이유다.
    # 2회차에는 대부분이 auto_fold(재관측)라 out["bodies"]에 신규분만 담긴다. 이 앱 접두를
    # 통째로 지우고 그것만 되채우면, 개념은 병합으로 살아남는데 그 개념의 본문만 사라진다
    prev_bodies = rekey_bodies_to_canon(stack.get("bodies") or {},
                                        adj_doc.get("auto_fold"))
    merged_bodies = dict(prev_bodies)
    members = rekey_members_to_canon(members, adj_doc.get("auto_fold"))
    members = merge_members(members, members_from_canon(prev_bodies, owned=_owned))
    # ★A 조립층 — 게이트 인용 뒤에 조항 원문 조각을 잇는다. 인용은 감사 흔적이라 남기고,
    # 조각이 실제 지식 본체다(시금석: 원본 문서가 삭제돼도 개념층만으로 읽힌다).
    _member_rows = rows + [{"sid": sid, "target": None}
                           for sid in sorted(members)
                           if sid not in {r["sid"] for r in rows}]
    assembled = assemble_body_fragments(_member_rows, tier_a, members=members) if tier_a else {}
    # ★조립이 실제로 본 단위 — 축 2의 삭제 판정을 단위 단위로 하기 위한 근거.
    _observed = {sid: {str(f.get("key") or "").split("|", 1)[0]
                       for f in frs if str(f.get("key") or "") != "quote"}
                 for sid, frs in assembled.items()}
    # 조립분은 승격 sid뿐 아니라 **재관측 sid**에도 붙는다 — out["bodies"]에는 승격분만
    # 있으므로 조립된 sid 전체를 합집합으로 돈다(위 _member_rows와 짝).
    new_bodies = {sid: list(out["bodies"].get(sid) or []) + assembled.get(sid, [])
                  for sid in set(out["bodies"]) | set(assembled)}
    for sid, frs in new_bodies.items():
        if _owned(sid):
            merged_bodies[sid] = frs
        else:
            have = {f.get("key") for f in merged_bodies.get(sid) or []}
            merged_bodies[sid] = list(merged_bodies.get(sid) or []) +                 [f for f in frs if f.get("key") not in have]
    bodies = {k: merged_bodies[k] for k in sorted(merged_bodies)}
    # ★조각 tombstone — 이번 조립에서 못 만든 조각은 지우지 않고 삭제 표시한다
    if tier_a:
        # ★축 2 — 갱신된 조각은 현행으로 올리고 옛 조각은 이력으로 내린다(사라지지 않는다).
        # (¬) '왜'는 결정 원장의 영향 조항 링크로 붙인다 — 없으면 비운다.
        why = supersede_reasons(events) if events else None
        scoped_prev = {k: v for k, v in prev_bodies.items() if _owned(k)}
        scoped_new = {k: v for k, v in bodies.items() if _owned(k)}
        # 승격분은 완전한 뷰(게이트 인용+조립), 재관측분은 members가 실은 조각만 = 부분.
        _partial = {sid for sid in scoped_new if sid not in set(out["bodies"])}
        # ★관측 우주 = 이 promote가 실제로 볼 수 있는 tier_a 단위 전부.
        # 교차앱 조각(다른 앱 단위가 이 개념의 member)은 이 집합 밖이라 삭제 판정을
        # 유보한다 — 볼 수 없는 것은 없어진 게 아니다(확산 묶음 3 예측 → regen 실화).
        stamped = fold_fragment_versions(scoped_prev, scoped_new,
                                         at=snap or "unknown", why=why, partial=_partial,
                                         observed_units=_observed,
                                         visible_units={a["anchor"] for a in tier_a})
        bodies.update(stamped)
        bodies = {k: bodies[k] for k in sorted(bodies)}

    held = {}
    for k in ("candidate", "ambiguous", "gap"):
        held[k] = _replace_app_slice(
            (stack.get("held") or {}).get(k, []), out["held"][k],
            lambda h: _owned(h["sid"]), lambda h: h["sid"])

    # provenance 정직화: 이전 판정 원장 출처 주장은 병합 후엔 부정확 — 유지 안 함.
    # 구 promoted/relations/held(카운트) 키도 "이번 실행"→"스택 총수"로 의미가 바뀌므로
    # 총수 명명(*_total)으로 대체, 조용한 의미 변질을 막는다.
    meta = dict(stack.get("meta") or {})
    meta.pop("source", None)
    for old_key in ("promoted", "relations", "held"):
        meta.pop(old_key, None)
    # ★보존 계측 — auto_fold(재관측) target이 정본에 없으면 그 하위개념은 승격도 갱신도
    # 되지 않고 증발한다(build_dispositions는 queue+carried만 순회, stamp_last_seen은 찍을
    # 노드가 없다). 정렬기가 개념을 Tier A 조항에 붙일 때 벌어지며 조항 구조가 좋은 앱일수록
    anchors = {c["anchor"] for c in concepts}
    dangling = sorted(x["sid"] for x in (adj_doc.get("auto_fold") or [])
                      if x.get("target") not in anchors)
    if unresolved:
        meta["unresolved_governed_by"] = sorted(unresolved, key=lambda x: x["sid"])
    else:
        meta.pop("unresolved_governed_by", None)
    if skipped:
        meta["skipped"] = skipped
    else:
        meta.pop("skipped", None)
    meta.update({"generator": "structure_app.run_promote", "last_promoted_app": app,
                "promoted_total": len(concepts), "relations_total": len(relations),
                "held_total": {k: len(v) for k, v in held.items()},
                "dangling_auto_fold": dangling})
    # 불변식 8 — 쓰기 직전에 잰다. 병합으로 해소했으니 여기서는 0이어야 정상이고,
    # 0이 아니면 병합이 못 미친 경로가 있다는 뜻이라 조용히 넘기지 않는다.
    uniq = anchor_uniqueness_report(concepts)
    if n_collapsed:
        meta["collapsed_duplicate_anchors"] = n_collapsed
    if not uniq["ok"]:
        meta["duplicate_anchors"] = uniq["duplicates"]
        print(f"promote {app}: ★불변식 8 위반 — anchor 중복 {len(uniq['duplicates'])}건")
    # 불변식 10 — 모든 본문 키는 실재하는 개념을 가리킨다.
    # 조각이 사라지지 않고 **자리만 틀린** 사고는 총량 게이트로 영원히 안 잡힌다.
    orphan = stranded_bodies(concepts, bodies)
    if orphan:
        meta["stranded_bodies"] = orphan
        print(f"promote {app}: ★불변식 10 위반 — 개념 없는 본문 키 {len(orphan)}건: "
              f"{', '.join(orphan[:5])}")
    else:
        meta.pop("stranded_bodies", None)
    if snap:
        meta["source_sha"] = snap        # 정본이 어느 시점을 보고 있나(최신성 게이트 입력)
    yaml.safe_dump({"meta": meta, "concepts": concepts, "relations": relations,
                    "bodies": bodies, "held": held},
                    open(stack_path, "w"), allow_unicode=True, sort_keys=False)
    n_auto = sum(1 for r in rows if r["disposition"] == "auto_adopt")
    n_review = sum(1 for r in rows if r.get("needs_review"))
    print(f"promote {app}: 편입 {len(out['concepts'])} (자동 {n_auto} · 사후리뷰 {n_review}) "
          f"· 재관측 {n_seen} · 관계 {len(out['relations'])} · 보류 {out['stats']['held']}"
          f" · 증발 {len(dangling)}"
          + (f" · 미실행 {sorted(skipped)}" if skipped else "")
          + f" → {stack_path.name}")
    return out


# ── CLI — ingest|prep|fold|promote 서브커맨드 배선 ──────────────────────────
# 각 서브커맨드는 위 순수 코어(prep_plan/fold_plan/build_dispositions 등)를 그대로
# 감싸는 I/O 다리(run_ingest_cli/run_prep/run_fold/run_promote) 호출만 한다.


_USAGE = ("usage: structure_app.py ingest|prep|fold|promote|brief|metrics|retire|absorb|drift|how|impact|recent|reproduce|crosscheck|view <corpus> <app> "
          "[--scope S] [--snap SHA] [--prev PATH] [--prev-dir DIR] [--src DIR] [--force]\n"
          "       brief:  --why (이력 평면까지 — 기본은 현행만)\n"
          "       metrics: <corpus> — 정본 지표를 canon/metrics.yaml에 남기고 직전과 대조(불변식 9)\n"
          "       view: <corpus> — 정본을 canon/canon-viewer.html 한 파일로(더블클릭)\n"
          "       how <corpus> <개념>   impact <corpus> <조항|개념>   recent <corpus> [앱]\n"
          "       prep:   --force-extract (벤치마크: 안 바뀐 섹션도 전건 재추출·계보 힌트 유지)\n"
          "       absorb: --legacy <bodies.yaml> (구 계보 본문 1회성 흡수)")


#: 코퍼스 축 명령 — 정본 전체를 보고 앱을 고르지 않는다(3인자 허용).
#: ★`crosscheck`가 여기 없어서 스윕이 앱 하나를 억지로 넘겼고, 그 앱 scope로 좁혀
CORPUS_LEVEL = ("metrics", "view", "crosscheck", "drift", "reproduce")


def needs_app(cmd):
    """이 명령이 앱을 요구하나. 코퍼스 축이면 False."""
    return cmd not in CORPUS_LEVEL


def _flag(argv, name):
    """플래그 값 조회 — 트레일링 플래그(값 없이 끝남)는 IndexError 대신 usage SystemExit."""
    if name in argv:
        i = argv.index(name)
        if i + 1 >= len(argv):
            raise SystemExit(_USAGE)
        return argv[i + 1]
    return None


def main(argv):
    """python3 structure_app.py ingest <corpus> <app> --src DIR [--scope S] [--force]
       python3 structure_app.py prep <corpus> <app> [--scope S] [--snap SHA] [--prev PATH]
       python3 structure_app.py fold <corpus> <app> [--scope S] [--prev-dir DIR]
       python3 structure_app.py promote <corpus> <app> [--scope S] [--owner-only]
       python3 structure_app.py brief <corpus> <app> [--scope S] [--snap SHA] [--as-of D]
    ingest: corpus source 기준 --src 아래 *.md → probes/subconcept-<app>/sections.yaml
    기계 생성 초안(S0 다리, 기존 파일 있으면 거부 — 수기 저작물 보호). prep: sections+
    canon-context 산출(추출 에이전트 입력). fold: 판정 큐+자동 fold(기존 판정 이월,
    재판정 0) — 증분 2회차는 --prev-dir로 이전 회차 subconcepts/align-proposals 이월.
    promote: 판정 완료분을 depth-stack.yaml에 편입(S4 다리)."""
    _need = 3 if (len(argv) > 1 and not needs_app(argv[1])) else 4
    if len(argv) < _need or argv[1] not in ("ingest", "prep", "fold", "promote", "brief",
                                            "metrics", "retire", "absorb", "drift",
                                            "how", "impact", "recent", "reproduce",
                                            "crosscheck", "consolidate", "view"):
        raise SystemExit(_USAGE)
    cmd, corpus = argv[1], argv[2]
    app = argv[3] if len(argv) > 3 and not argv[3].startswith("-") else ""
    import os
    FX = Path(os.environ.get("LKL_FIXTURES")
              or Path(__file__).resolve().parent / "fixtures")
    base = work_dir(corpus, app, root=FX)
    # --scope 미지정 시 registry 선언에서 채운다(없으면 종전대로 app 이름 그대로).
    from corpus import app_scopes_for
    declared = app_scopes_for(corpus).get(app)

    def _scope():
        return _flag(argv, "--scope") or declared or app
    if cmd == "ingest":
        app_scope = _scope()
        src_rel = _flag(argv, "--src")
        if not src_rel:
            raise SystemExit(_USAGE)
        reg = load_registry()
        cfg = (reg.get("corpora") or {}).get(corpus) or {}
        if not cfg.get("source"):
            raise SystemExit(f"미등록 corpus 또는 source 미선언: {corpus}")
        source_root = (Path(__file__).parent / cfg["source"]).resolve()
        from corpus import concept_formats_for
        fmts = concept_formats_for(corpus, reg)
        # 스칼라 마크다운 단독 선언은 레거시 경로 유지(옛 원장 재현성 보존).
        if set(fmts.values()) == {"markdown-sections"} and len(fmts) == 1:
            fmts = None
        run_ingest_cli(source_root, src_rel, base, app_scope, force="--force" in argv,
                       exclude=concept_exclude_for(corpus, reg), formats=fmts)
    elif cmd == "prep":
        app_scope = _scope()
        sha = _flag(argv, "--snap")
        canon = yaml.safe_load(open(
            tier_a_path(corpus, sha, root=FX)))["concepts"] \
            if sha else []
        prev_path = _flag(argv, "--prev")
        prev_sections = prev_subs = None
        if prev_path:
            prev_sections = yaml.safe_load(open(prev_path))["sections"]
            # 계보 힌트용 이전 회차 개념 — sections.yaml 옆의 subconcepts.yaml(같은 디렉토리)
            # 이 있으면 쓰고, 없으면 힌트 없이 진행(1회차·수기 probe 호환).
            prev_sub_path = Path(prev_path).parent / "subconcepts.yaml"
            if prev_sub_path.exists():
                prev_subs = yaml.safe_load(open(prev_sub_path))["subconcepts"]
        # 루프 닫기 — 이 코퍼스 정본 깊은층(Tier B)을 canon 주입원에 합친다.
        # 없으면(첫 회차·신규 코퍼스) 종전대로 Tier A만. --tier-a-only로 강제 제외.
        stack_path = canon_path(corpus, root=FX)
        stack = (yaml.safe_load(open(stack_path))
                 if stack_path.exists() and "--tier-a-only" not in argv else None)
        run_prep(base, app_scope, canon, corpus=corpus, prev_sections=prev_sections, snap=sha,
                 prev_subconcepts=prev_subs, stack=stack,
                 force_extract="--force-extract" in argv)
    elif cmd == "fold":
        # ★fold의 scope는 **sid 접두(앱 슬러그)**다 — 정본 scope가 아니다. align-proposals의
        # sid가 `<슬러그>#<anchor>` 형식이라(예 `alert#sc-x`) 여기에 정본 scope
        # (`prime-commerce/summit/alert`)를 넣으면 전건 phantom+누락으로 개념 수의 2배
        fold_stack_path = canon_path(corpus, root=FX)
        from corpus import work_scopes_for, canon_extensions_path
        run_fold(base, _flag(argv, "--scope") or work_scopes_for(corpus).get(app) or app,
                 ext_path=canon_extensions_path(corpus, root=FX),
                 prev_dir=_flag(argv, "--prev-dir"),
                 stack=(yaml.safe_load(open(fold_stack_path))
                        if fold_stack_path.exists() and "--tier-a-only" not in argv
                        else None))
    elif cmd == "absorb":
        # 1회성 마이그레이션 — 구 계보(예: l1-snapshots/<sha>/bodies/bodies.yaml)의 조립
        # 본문을 현 정본에 잇는다. 미연결분은 probe 옆 원장으로 남겨 사람 판정에 넘긴다.
        legacy = _flag(argv, "--legacy")
        if not legacy:
            raise SystemExit(_USAGE)
        run_absorb(canon_path(corpus, root=FX), legacy,
                   base / "unbridged-legacy.yaml")
    elif cmd == "drift":
        # S6 — 정본 두 스냅샷 비교. --prev로 이전 정본을 준다(없으면 자기 자신=변화 0).
        cur = yaml.safe_load(open(canon_path(corpus, root=FX))) or {}
        from corpus import ledger_dir as _ld
        prev_p = _flag(argv, "--prev") or previous_round(_ld(corpus, root=FX) / "rounds")
        prev = yaml.safe_load(open(prev_p)) if prev_p else None
        if prev is None:
            print("  ⚠ 직전 회차 정본 없음 — 낡음 감시는 이번 회차부터 잰다(비교 대상 없음)")
            prev = cur
        sup = {}
        for cand in sorted((FX / corpus / "ledger" / "decisions").glob("*/events.auto.yaml")) \
                if (FX / corpus / "ledger" / "decisions").exists() else []:
            for e in (yaml.safe_load(open(cand)) or {}).get("events") or []:
                if e.get("type") == "supersede" and e.get("target") and e.get("by"):
                    sup[e["target"]] = e["by"]
        # 최신성 — 정본이 최신 스냅샷을 보고 있나, 층끼리 시점이 갈리지 않나.
        from corpus import snapshot_index, integrity_path
        recs = snapshot_index(corpus, root=FX)
        pick = newest_snapshot(recs)
        fresh = freshness_report((cur.get("meta") or {}).get("source_sha"),
                                 available=[r["sha"] for r in recs],
                                 newest=pick["newest"], undated=pick["undated"])
        if not fresh["fresh"]:
            print(f"  ⚠ 최신성: 정본 {fresh['canon_sha']} · 최신 스냅샷 {fresh['newest']}"
                  + (f" · 시점 갈린 층 {fresh['stale_layers']}" if fresh["stale_layers"] else "")
                  + (f" · 시각 없는 스냅샷 {fresh['undated']}" if fresh["undated"] else ""))
        rep = drift_report(prev, cur, supersedes=sup)
        rep["freshness"] = fresh
        out = canon_dir(corpus, root=FX) / "drift.yaml"
        yaml.safe_dump(rep, open(out, "w"), allow_unicode=True, sort_keys=False)
        print(f"drift {corpus}: 낡은 개념 {len(rep['stale'])} · 낡은 권위 인용 "
              f"{len(rep['stale_citations'])} · 조각 {rep['stats']} → {out.name}")
        # S6-b 침식 감시 — brief가 읽는 자리에 남긴다 배선).
        snap = fresh["canon_sha"] or pick["newest"]
        try:
            import corpus as _cp
            concepts = (yaml.safe_load(open(_cp.tier_a_path(corpus, snap, root=FX)))
                        or {}).get("concepts") or []
            from l1_integrity import _load_decisions
            decisions = _load_decisions(corpus, Path(__file__).parent)
            cfg = (_cp.load_registry().get("corpora") or {}).get(corpus) or {}
            ip = write_integrity(canon_dir(corpus, root=FX), concepts, decisions,
                                 archive_segments=cfg.get("archive_segments"))
            doc = yaml.safe_load(open(ip)) or {}
            print(f"  침식 @{snap}: 죽은 참조 {len(doc.get('dead') or [])} · "
                  f"모호 {len(doc.get('ambiguous') or [])} · "
                  f"아카이브 {len(doc.get('archived') or [])} → {ip.name}")
        except Exception as e:
            # 조용한 미실행 금지 — 못 돌면 왜 못 돌았는지 찍는다.
            print(f"  ⚠ 침식 감시 미실행: {type(e).__name__}: {e}")
    elif cmd == "consolidate":
        from consolidate import apply_consolidation
        import glob as _g
        doc = yaml.safe_load(open(canon_path(corpus, root=FX))) or {}
        n0 = len(doc.get("concepts") or [])
        for pf in sorted(_g.glob(str(base / "consolidation-proposals*.yaml"))):
            props = (yaml.safe_load(open(pf)) or {}).get("proposals") or []
            doc = apply_consolidation(doc, props, prefix=f"{app}#")
            doc.pop("_unresolved", None)
        canon_path(corpus, root=FX).write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"consolidate {corpus}/{app}: 개념 {n0} → {len(doc.get('concepts') or [])}")
    elif cmd == "reproduce":
        # 불변식 4 — 재생을 한 번 더 돌린 뒤 사본과 대조한다(같은 입력 → 같은 산출).
        ref = _flag(argv, "--against")
        first = yaml.safe_load(open(ref)) or {}
        again = yaml.safe_load(open(canon_path(corpus, root=FX))) or {}
        rep = reproducibility_report(first, again)
        print(f"reproduce {corpus}: {'동일' if rep['ok'] else '★차이'}"
              f" · byte_identical={rep['byte_identical']}")
        for dfl in rep["diffs"]:
            print(f"  {dfl['metric']}: {dfl['first']} → {dfl['again']}")
        if not rep["ok"]:
            raise SystemExit(1)
    elif cmd == "crosscheck":
        # 층간 대조 — 같은 개념 아래 조항과 화면이 다른 값을 말하는가. 결정론·LLM 0.
        import crosscheck as _cc
        doc = yaml.safe_load(open(canon_path(corpus, root=FX))) or {}
        snap = _flag(argv, "--snap") or (doc.get("meta") or {}).get("source_sha")
        tp = tier_a_path(corpus, snap, root=FX) if snap else None
        kinds = {c["anchor"]: c.get("kind")
                 for c in ((yaml.safe_load(open(tp)) or {}).get("concepts") or [])} \
            if tp and tp.exists() else {}
        scope = _flag(argv, "--scope") or (app_scopes_for(corpus).get(app) if app else None)
        rep = _cc.crosscheck_canon(doc, kinds, scope=scope)
        from shared_ground import shared_ground_report as _sg
        sg = _sg(doc.get("concepts"), doc.get("bodies"), doc.get("relations"))
        # 불변식 14 — 개념 **간** 축. 위 대조는 한 개념 안만 본다.
        rep["ungrounded_pairs"] = sg["ungrounded_pairs"]
        rep["cross_concept_ok"] = sg["ok"]
        names = {c["anchor"]: c.get("name") for c in doc.get("concepts") or []}
        print(_cc.render(rep, names))
        if not sg["ok"]:
            print(f"\n★개념 간 — 같은 코드를 말하는데 안 이어진 확정 주장 {len(sg['ungrounded_pairs'])}쌍:")
            for p in sg["ungrounded_pairs"][:10]:
                print(f"  {p['a']} ↔ {p['b']}  ({', '.join(p['shared_units'])})")
        out = canon_dir(corpus, root=FX) / "crosscheck.yaml"
        yaml.safe_dump(rep, open(out, "w"), allow_unicode=True, sort_keys=False)
    elif cmd in ("how", "impact", "recent"):
        # 소비 경로. 읽기 전용·결정론·LLM 0.
        import ask as _ask
        doc = yaml.safe_load(open(canon_path(corpus, root=FX))) or {}
        events = []
        for cand in sorted((FX / corpus / "ledger" / "decisions").glob("*/events.auto.yaml")):
            events += (yaml.safe_load(open(cand)) or {}).get("events") or []
        if cmd == "how":
            # 출처 층을 갈라 보여주려면 각 단위의 kind가 필요하다 — Tier A 스냅샷에서 읽는다.
            snap = _flag(argv, "--snap") or (doc.get("meta") or {}).get("source_sha")
            tp = tier_a_path(corpus, snap, root=FX) if snap else None
            kinds = {c["anchor"]: c.get("kind")
                     for c in ((yaml.safe_load(open(tp)) or {}).get("concepts") or [])} \
                if tp and tp.exists() else {}
            print(_ask.render_how(_ask.ask_how(doc, app, why="--why" in argv,
                                               unit_kinds=kinds), events))
        elif cmd == "impact":
            print(_ask.render_impact(_ask.ask_impact(doc, app)))
        else:
            scope = _flag(argv, "--scope") or (app_scopes_for(corpus).get(app) if app else None)
            print(_ask.render_recent(_ask.ask_recent(doc, scope=scope), events))
    elif cmd == "retire":
        # 앱 슬라이스를 정본에서 빼서 ledger/legacy로 — 버리되 보존(0에서 재구축 전 단계).
        from corpus import ledger_dir
        cur = yaml.safe_load(open(canon_path(corpus, root=FX))) or {}
        at = _flag(argv, "--snap") or (cur.get("meta") or {}).get("source_sha") or "unknown"
        reason = _flag(argv, "--reason") or "0에서 재구축"
        from corpus import work_dir as _wd
        out = retire_slice(canon_path(corpus, root=FX), app,
                           ledger_dir(corpus, root=FX) / "legacy", at=at, reason=reason,
                           work_dir=_wd(corpus, app, root=FX))
        if out is None:
            print(f"retire {app}: 정본에 이 앱 슬라이스가 없다 — 아무것도 바꾸지 않았다")
        else:
            arch = yaml.safe_load(open(out)) or {}
            print(f"retire {app}: 개념 {len(arch['concepts'])} · 본문 {len(arch['bodies'])}"
                  f" · 관계 {len(arch['relations'])} → {out.relative_to(FX)}")
    elif cmd == "metrics":
        # 불변식 9 — 정본 자체를 재서 파일로 남기고 직전과 대조한다(코드가 아니라 산출물).
        # STATUS에 적는 숫자는 여기서만 인용한다. 기억이 아니라 파일이 근거가 되게.
        doc = yaml.safe_load(open(canon_path(corpus, root=FX))) or {}
        from corpus import archive_segments_for as _arch
        cur = canon_metrics(doc, archive_segments=_arch(corpus),
                            ingested_docs=_ingested_docs(doc))
        out = canon_dir(corpus, root=FX) / "metrics.yaml"
        prev = ((yaml.safe_load(open(out)) or {}).get("metrics")) if out.exists() else None
        _ret = [r for r in ((doc.get("meta") or {}).get("retired") or [])
                if r.get("at") == cur.get("source_sha")]
        gate = metrics_gate(prev, cur, retired=_ret)
        yaml.safe_dump({"corpus": corpus, "metrics": cur, "gate": gate},
                       open(out, "w"), allow_unicode=True, sort_keys=False)
        print(f"metrics {corpus}: 개념 {cur['concepts']} · 관계 {cur['relations']} · "
              f"본문 {cur['body_chars']}자 · 현행 {cur['current_filled']} · "
              f"무명 {cur['nameless']} · scope {cur['scopes']} · 증발 {cur['dangling_auto_fold']}"
              f" → {out.name}")
        if not gate["ok"]:
            print(f"  ★불변식 9 위반 — 정본이 줄었다: {gate['regressions']}")
            raise SystemExit(1)
    elif cmd == "view":
        # 정본을 사람이 보는 표면. 새 데이터는 만들지 않고 있는 것만 합친다.
        from viewer import build_view_model
        from viewer_html import render_html
        from corpus import kind_families
        reg = load_registry()
        src = (reg.get("corpora", {}).get(corpus) or {}).get("source") or ""
        cdir = canon_dir(corpus, root=FX)
        # ★경로는 상대로 싣는다 — 절대경로를 박으면 HTML이 기계마다 달라지고(재생 diff),
        #   만든 사람의 홈 경로가 산출물에 남는다. 원천은 HTML 위치 기준, 출처는 engine/ 기준.
        engine_dir = Path(__file__).resolve().parent
        model = build_view_model(cdir, corpus=corpus,
                                 families=kind_families(reg),
                                 source_root=(os.path.relpath(engine_dir / src, cdir.resolve())
                                              if src else ""),
                                 generated_from=os.path.relpath(cdir.resolve(), engine_dir))
        out = cdir / "canon-viewer.html"
        html = render_html(model)
        out.write_text(html, encoding="utf-8")
        mb = len(html.encode()) / 1048576
        print(f"view {corpus}: 개념 {len(model['concepts'])} · 어긋남 "
              f"{len(model['issues'])} · {mb:.1f}MB → {out}")
        for w in model["warnings"]:
            print(f"  ⚠ {w}")
        if mb > 8:
            print(f"  ⚠ {mb:.1f}MB — 8MB 문턱 초과. 압축을 논할 때다(설계 §3-5)")
    elif cmd == "brief":
        # 소비 경로(설계 §3 P2) — 읽기 전용, 기존 층만 조립. 신규 저장소 0·LLM 0.
        import brief as _brief
        as_of = _flag(argv, "--as-of") or "2030-12-31"
        doc = _brief.load_and_build(corpus, app, _scope(), _flag(argv, "--snap"),
                                    valid_at=as_of, known_at=as_of, root=FX,
                                    why="--why" in argv)
        print(_brief.render(doc))
    else:
        app_scope = _scope()
        stack = canon_path(corpus, root=FX)
        # Tier A 스냅샷 — 본문 조립의 원문 출처. SHA는 prep이 manifest에 남긴 것을 쓰고
        # (--snap으로 덮어쓸 수 있다), 없으면 조립 없이 종전대로 quote만.
        man = base / "extract-manifest.yaml"
        snap = _flag(argv, "--snap") or \
            ((yaml.safe_load(open(man)) or {}).get("snap") if man.exists() else None)
        snap_path = tier_a_path(corpus, snap, root=FX) if snap else None
        tier_a = (yaml.safe_load(open(snap_path))["concepts"]
                  if snap_path and snap_path.exists() else None)
        if snap and stack.exists():
            from corpus import snapshot_index as _si
            _order = check_snapshot_order(
                snap, (yaml.safe_load(open(stack)) or {}).get("meta", {}).get("source_sha"),
                _si(corpus, root=FX))
            if not _order["ok"] and "--allow-older" not in argv:
                raise SystemExit(
                    f"거부: 정본은 {_order['canon']}({_order['canon_at']})에서 만들어졌는데 "
                    f"{_order['requested']}({_order['requested_at']})로 재생하려 한다 — "
                    f"현행 본문이 옛 텍스트로 덮이고 지금 본문이 이력으로 밀려난다.\n"
                    f"  registry `canon_snap` 선언이 뒤처졌는지 먼저 확인하라. "
                    f"의도한 롤백이면 --allow-older.")
        # ★결정층 이벤트 — 현행 평면의 입력. brief와 같은 원장에서 같은 방식으로 읽는다.
        events = []
        for cand in sorted((FX / corpus / "ledger" / "decisions").glob("*/events.auto.yaml")):
            events += (yaml.safe_load(open(cand)) or {}).get("events") or []
        # 기본은 자동 편입(게이트 통과분 전부). --owner-only는 구 계약(판정 완료분만) 복귀.
        run_promote(base, app, stack, app_scope,
                    auto_adopt="--owner-only" not in argv, tier_a=tier_a, snap=snap,
                    events=events or None)


if __name__ == "__main__":
    import sys
    main(sys.argv)
