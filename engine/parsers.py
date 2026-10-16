"""Decision-content parsers (진화 레이어). decision_format별 dispatch.

전략: docs/2-method/extraction-strategy.md — 형식은 표면, 밑바닥은 하나(SourceDecision).
  Tier A(형식 어댑터, 여기): 아는 하우스 형식을 결정론적으로 → SourceDecision.
  Tier B(LLM 추출기, 미구현): 비정형/모르는 형식 → 같은 SourceDecision, confidence 표시.
둘 다 **같은 공통 스키마**를 뱉어 하류(reducer·adjudication)를 형식-무관하게 만든다.

Track-E-lite 원칙(ingest_wevolley와 동일): 신뢰 가능한 **스켈레톤**만 자동 추출.
target/option 매핑·delta 종류 같은 **의미**는 지어내지 않고 adjudication으로 남긴다(§10).

# ── 공통 출력 스키마 (Tier A/B 공통 목표) ──────────────────────────────
# SourceDecision = {
#   anchor:     str            # 원본 식별자 (D-7318 · 0009 · LLM 부여 지역 id)
#   time:       str            # valid_at (원문 날짜)
#   content:    str            # 결정 문장 (원문 보존)
#   status:     str | None     # 반영/lifecycle 힌트
#   articles:   [str]          # 영향 조항·참조
#   relations:  [(kind, target_anchor)]   # ('supersedes', 'D-7318') 등 감지된 관계
#   provenance: {corpus, scope, source_file?, ...}
#   confidence: 'high' | 'low' # 스켈레톤=high, 의미 추론=low
# }
# (현재 corpdoc-table은 이 계약의 핵심 필드를 채운다. 완전 정렬은 extraction-strategy §다음.)
"""
from __future__ import annotations

import ast
import re

_ARTICLE = re.compile(r"[A-Z][A-Z0-9]*-\d+")
# 결정 ID는 구 스킴 D-N·신 스킴 <APP>-D-N 병행 인식 (epoch 경계 — decision_alias 참조)
_DEC_ID = r"(?:[A-Z][A-Z0-9]*-)?D-\d+"
_ROW_ID = re.compile(r"^\|\s*(" + _DEC_ID + r")\s*\|")
_SUPERSEDED_BY = re.compile(r"→\s*\*{0,2}(" + _DEC_ID + r")")   # "→ **D-8812" = 이 행이 D-8812로 대체됨
_SUPERSEDES = re.compile(r"(" + _DEC_ID + r")\s*supersede")     # "D-7318 supersede" = 이 행이 D-7318를 대체


def parse_corpdoc_decisions(md_text, scope=None):
    """decisions-log.md의 `## 결정 이력 (D-N)` 표 → 결정 스켈레톤 + supersede 관계.

    표 컬럼: ID | 날짜 | 결정 내용 | 출처 | 영향 조항 | 반영 상태 | 비고
    (중간 셀에 '|'가 있어도 견디게 양끝 기준으로 집는다.)
    반환: {"decisions": [...], "supersede_relations": [(newer, older), ...]}  (newer가 older를 대체)
    """
    decisions = []
    relations = set()
    for raw in md_text.splitlines():
        line = raw.strip()
        if not _ROW_ID.match(line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 7:
            continue
        did, date = cells[0], cells[1]
        articles_cell, status, note = cells[-3], cells[-2], cells[-1]   # 양끝 기준 (content/source 파이프 견딤)
        content = "|".join(cells[2:-4])                # 결정 문장 원문 보존 (출처 셀 직전까지)
        superseded_by = None
        m = _SUPERSEDED_BY.search(status) or _SUPERSEDED_BY.search(note)
        if m:
            superseded_by = m.group(1)
            relations.add((m.group(1), did))               # newer(→대상)가 did를 대체
        for m2 in _SUPERSEDES.finditer(note):
            older = m2.group(1)
            if older != did:
                relations.add((did, older))                # did가 older를 대체
        decisions.append({
            "decision_id": did, "date": date, "scope": scope, "content": content,
            "articles": _ARTICLE.findall(articles_cell),
            "status": status, "note": note,
            "superseded_by": superseded_by,
            "reflected": ("반영완료" in status) and ("~~" not in status),
        })
    return {"decisions": decisions, "supersede_relations": sorted(relations)}


# ── L1 개념층 (SourceConcept) ──────────────────────────────────────────
# 1-rules 조항 문서: `### [INV-NN] 규칙 본문` + 근거(D-N)·참조(`[INV-NN]`) 불릿 + 변경 이력 표.
# SourceConcept = { anchor, kind, content(원문), section, scope, refs{decisions,articles},
#                   fields{근거|참조|...}, line(왕복 보존), confidence }
_CONCEPT_HEAD = re.compile(r"^### \[([A-Z][A-Z0-9]*-\d+)\]\s*(.+)$")
_BRACKET_REF = re.compile(r"\[([A-Z][A-Z0-9]*-\d+)\]")
_DECISION_REF = re.compile(r"\b" + _DEC_ID + r"\b")   # 전체형 우선 매치 (INV-D-7286 → 통째)
_FM_VERSION = re.compile(r'^version:\s*"([^"]+)"', re.M)
_DATE_CELL = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_corpdoc_rules(md_text, scope=None):
    """1-rules 조항 문서 → {"concepts": [...], "changelog": [...], "version": ...}.

    Track-E-lite 동일 원칙: 구조(조항 헤더·불릿 라벨·표)만 신뢰해 추출하고
    의미(조항 관계의 종류, GAP 판정)는 지어내지 않는다. 전부 confidence=high 스켈레톤.
    """
    concepts, changelog = [], []
    cur, section, in_changelog = None, None, False
    for i, raw in enumerate(md_text.splitlines(), 1):
        line = raw.rstrip()
        if line.startswith("## "):
            section = line[3:].strip()
            in_changelog = "변경 이력" in section
            cur = None
            continue
        m = _CONCEPT_HEAD.match(line)
        if m:
            cur = {"anchor": m.group(1), "kind": "article", "content": m.group(2).strip(),
                   "section": section, "scope": scope, "line": i,
                   "refs": {"decisions": [], "articles": []}, "fields": {},
                   "confidence": "high"}
            concepts.append(cur)
            continue
        if in_changelog and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 4 and _DATE_CELL.match(cells[0]):
                note = cells[2]
                changelog.append({"date": cells[0], "version": cells[1], "note": note,
                                  "decisions": sorted(set(_DECISION_REF.findall(note))),
                                  "articles": sorted(set(_BRACKET_REF.findall(note)))})
            continue
        if cur is not None and line.strip():
            stripped = line.strip()
            # 조항 밑 표 행 보존 (round 2 ② — 행 단위·원문 무수정, 구분선 제외)
            if stripped.startswith("|"):
                if not re.match(r"^\|[\s:|-]+\|$", stripped):
                    cur.setdefault("table", []).append(stripped)
            if stripped.startswith("- ") and ":" in stripped:
                label, _, val = stripped[2:].partition(":")
                if len(label) <= 12:                       # 불릿 라벨(근거·사례·참조·제약·GAP류)만
                    cur["fields"][label.strip()] = val.strip()
            for d in _DECISION_REF.findall(stripped):
                if d not in cur["refs"]["decisions"]:
                    cur["refs"]["decisions"].append(d)
            for a in _BRACKET_REF.findall(stripped):
                if a != cur["anchor"] and a not in cur["refs"]["articles"]:
                    cur["refs"]["articles"].append(a)

    ver = _FM_VERSION.search(md_text)
    return {"concepts": concepts, "changelog": changelog,
            "version": ver.group(1) if ver else None}


# ── spec.md (L1 kind 확장) ─────────────────────────────────────────────
_BACKTICK = re.compile(r"`([^`]+)`")
_SPEC_FIELD_SECTION = "리소스 · 데이터 정의"
_SPEC_ENUM_SECTION = "상태값 목록"
_SPEC_SKIP_SECTIONS = {"변경 이력"}
_TABLE_HEADER_CELLS = {"리소스/엔티티", "리소스", "날짜", "값", "그룹"}


def _row_cells(line):
    s = line.strip()
    if not s.startswith("|"):
        return None
    cells = [c.strip() for c in s.strip("|").split("|")]
    if not cells or cells[0] in _TABLE_HEADER_CELLS or set(cells[0]) <= {"-", " "}:
        return None
    return cells


def _collect_refs(concept, text):
    for d in _DECISION_REF.findall(text):
        if d not in concept["refs"]["decisions"]:
            concept["refs"]["decisions"].append(d)
    for a in _BRACKET_REF.findall(text):
        if a != concept["anchor"] and a not in concept["refs"]["articles"]:
            concept["refs"]["articles"].append(a)


def parse_corpdoc_spec(md_text, scope=None):
    """spec.md → {"concepts": [...], "version": ...}. 구조(고정 헤딩·표)만 신뢰하는 스켈레톤."""
    concepts, flags = [], []
    enums = {}                                       # 상태값은 리소스별 집계
    section = None
    cur_sec = None                                   # 현재 spec_section 개념(산문 수집처)
    enum_sub = None                                  # 상태값 섹션의 ### 소제목 = 리소스 (alert 형태)
    field_mode = None                                # 필드 표 헤더 판별: canonical | unknown
    for i, raw in enumerate(md_text.splitlines(), 1):
        line = raw.rstrip()
        if line.startswith("## "):
            section = line[3:].strip()
            enum_sub = None
            field_mode = None
            cur_sec = None
            if section not in _SPEC_SKIP_SECTIONS:
                cur_sec = {"anchor": f"spec§{section}", "kind": "spec_section",
                           "content": section, "section": section, "scope": scope,
                           "line": i, "refs": {"decisions": [], "articles": []},
                           "confidence": "high"}
                concepts.append(cur_sec)
            continue
        if (cur_sec is not None and line.strip()
                and section not in (_SPEC_FIELD_SECTION, _SPEC_ENUM_SECTION)):
            st = line.strip()
            if not re.match(r"^\|[\s:|-]+\|$", st):
                cur_sec["content"] += "\n" + st
                _collect_refs(cur_sec, line)
        if section == _SPEC_FIELD_SECTION:
            if not line.strip().startswith("|"):
                field_mode = None                    # 표 사이 공백/문장 = 다음 표의 헤더 재판별
                continue
            cells = [x.strip() for x in line.strip().strip("|").split("|")]
            if set(cells[0]) <= {"-", " "}:
                continue
            if field_mode is None:                   # 표 첫 행 = 헤더 — 캐논 형태만 파싱
                if cells[0] == "리소스/엔티티":
                    field_mode = "canonical"
                else:
                    field_mode = "unknown"
                    flags.append(f"미지 표 형태: '리소스 · 데이터 정의' 헤더 {cells[:2]} — "
                                 f"Tier A 미지원, 지어내지 않고 건너뜀 (확장/adjudication 필요)")
                continue
            if field_mode == "canonical" and len(cells) >= 5:
                c = {"anchor": f"{cells[0]}.{cells[1]}", "kind": "field",
                     "content": cells[4], "section": section, "scope": scope,
                     "type": cells[2], "required": cells[3] == "O", "line": i,
                     "refs": {"decisions": [], "articles": []}, "confidence": "high"}
                _collect_refs(c, line)
                concepts.append(c)
        elif section == _SPEC_ENUM_SECTION:
            if line.startswith("### "):
                enum_sub = line[4:].strip()          # alert 형태: 소제목 = 리소스
                continue
            cells = _row_cells(line)
            if not cells:
                continue
            # 표 형태 3종 (실측): 3열 리소스|상태값|의미 / 2열 값|의미(소제목=리소스) / 2열 그룹|값
            resource = values_cell = meaning = None
            if len(cells) >= 3:
                resource, values_cell, meaning = cells[0], cells[1], cells[2]
            elif len(cells) == 2 and _BACKTICK.search(cells[0]) and enum_sub:
                resource, values_cell, meaning = enum_sub, cells[0], cells[1]
            elif len(cells) == 2 and _BACKTICK.search(cells[1]):
                resource, values_cell, meaning = cells[0], cells[1], ""
            if resource is None:
                continue
            c = enums.get(resource)
            if c is None:
                c = enums[resource] = {"anchor": resource, "kind": "state_enum",
                                       "content": "", "section": section, "scope": scope,
                                       "values": [], "value_notes": {}, "line": i,
                                       "refs": {"decisions": [], "articles": []},
                                       "confidence": "high"}
                concepts.append(c)
            for v in _BACKTICK.findall(values_cell):
                if v not in c["values"]:
                    c["values"].append(v)
                # 값별 행 note 보존 — 같은 행의 값들은 note 공유(행 밖 분해는 지어내지 않음)
                if meaning:
                    c["value_notes"][v] = meaning
            if meaning:
                c["content"] = (c["content"] + "; " if c["content"] else "") + meaning
            _collect_refs(c, values_cell + " " + meaning)

    ver = _FM_VERSION.search(md_text)
    return {"concepts": concepts, "flags": flags,
            "version": ver.group(1) if ver else None}


# ── 화면정의서 (L1 kind 확장 2차) ─────────────────────────────────────
# 담당자가 정책서와 다름(소유자 실무 지적) → author 보존 + 문서 자기기록 GAP을 1급 개념으로.
# 3 kind: screen(화면ID=anchor) · screen_section(## 단위) · gap(**GAP(유형):** 마커)
_SCREEN_ID = re.compile(r"화면ID:\s*\*\*([^*]+?)\*\*")
_GAP_MARK = re.compile(r"\*\*GAP\(([^)]*)\):?\*\*:?\s*(.*)")
_FM_AUTHOR = re.compile(r'^author:\s*"([^"]+)"', re.M)
_FM_TITLE = re.compile(r'^title:\s*"([^"]+)"', re.M)


def parse_corpdoc_screen(md_text, scope=None):
    """화면정의서 → {"concepts": [...], "flags": [...], "version": ...}.

    어느 쪽이 맞는지 판정하지 않는다 — GAP은 기록 그대로 개념화(불일치 판정은
    정책·화면 두 담당자의 adjudication 몫).
    """
    sid_m = _SCREEN_ID.search(md_text)
    title_m = _FM_TITLE.search(md_text)
    author_m = _FM_AUTHOR.search(md_text)
    flags = []
    if sid_m:
        anchor = sid_m.group(1).strip()
    else:
        anchor = f"screen:{title_m.group(1)}" if title_m else "screen:unknown"
        flags.append(f"화면ID 미선언 — anchor를 제목으로 대체({anchor}), 정본 편집 제안 후보")

    screen = {"anchor": anchor, "kind": "screen",
              "content": title_m.group(1) if title_m else "", "section": None,
              "scope": scope, "line": 1,
              "author": author_m.group(1) if author_m else None,
              "refs": {"decisions": [], "articles": []}, "confidence": "high"}
    concepts = [screen]
    cur_sec, gap_n = None, 0
    for i, raw in enumerate(md_text.splitlines(), 1):
        line = raw.rstrip()
        if line.startswith("## "):
            heading = line[3:].strip()
            if "변경 이력" in heading:
                cur_sec = None
                continue
            cur_sec = {"anchor": f"{anchor}§{heading}", "kind": "screen_section",
                       "content": heading, "section": heading, "scope": scope, "line": i,
                       "refs": {"decisions": [], "articles": []}, "confidence": "high"}
            # 헤딩 줄 자신의 참조도 걷는다 — `## 2. 보관 정책 \`[INV-55]\`` 처럼 조항
            _collect_refs(cur_sec, line)
            concepts.append(cur_sec)
            continue
        if cur_sec is not None and line.strip():
            cur_sec["content"] += "\n" + line.strip()
        gm = _GAP_MARK.search(line)
        if gm:
            gap_n += 1
            g = {"anchor": f"{anchor}.gap{gap_n}", "kind": "gap",
                 "gap_type": gm.group(1).strip(), "content": gm.group(2).strip(),
                 "section": cur_sec["section"] if cur_sec else None, "scope": scope,
                 "line": i, "refs": {"decisions": [], "articles": []}, "confidence": "high"}
            _collect_refs(g, line)
            concepts.append(g)
        if cur_sec is not None:
            _collect_refs(cur_sec, line)
        _collect_refs(screen, line)

    ver = _FM_VERSION.search(md_text)
    return {"concepts": concepts, "flags": flags,
            "version": ver.group(1) if ver else None}


PARSERS = {"corpdoc-table": parse_corpdoc_decisions,
           "corpdoc-rules": parse_corpdoc_rules,
           "corpdoc-spec": parse_corpdoc_spec,
           "corpdoc-screen": parse_corpdoc_screen}


def parse(decision_format, md_text, scope=None, **kw):
    """포맷별 dispatch. **어댑터마다 필요한 kwarg가 다르다** — 마크다운은 `doc_slug`,
    코드는 `module`을 받는다. 호출자가 포맷별로 분기하지 않게, 여기서 **대상 함수가
    받는 것만 넘긴다**(모르는 kwarg는 조용히 버린다)."""
    fn = PARSERS.get(decision_format)
    if fn is None:
        raise ValueError(f"미등록 decision_format: {decision_format}")
    import inspect
    accepted = inspect.signature(fn).parameters
    kw = {k: v for k, v in kw.items() if k in accepted}
    return fn(md_text, scope=scope, **kw)


# ── markdown-sections (범용 어댑터 — 설계: docs/2-method/markdown-corpus-adapter.md) ──
# ID 없는 마크다운의 기본 계열. anchor = <doc_slug>#<heading_slug> (doc-heading 스킴).
# anchor 안정성은 보장이 아니라 감시 대상 — 드리프트는 변경 축이 잡고 재바인딩 제안.
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")


def _heading_slug(text):
    t = re.sub(r"[#*`\[\]]", "", text).strip()
    return re.sub(r"\s+", "-", t)


def parse_markdown_sections(md_text, scope=None, doc_slug=None):
    """ID 없는 마크다운 → 섹션 단위 SourceConcept. 구조(헤딩)만 신뢰, 원문 무수정.
    동명 헤딩은 등장 순서로 -2, -3… 결정론 구분. 첫 헤딩 앞 서문 = #_preamble."""
    concepts, seen = [], {}

    def new_section(heading, level, line_no):
        hs = _heading_slug(heading) if heading else "_preamble"
        seen[hs] = seen.get(hs, 0) + 1
        if seen[hs] > 1:
            hs = f"{hs}-{seen[hs]}"
        c = {"anchor": f"{doc_slug}#{hs}", "kind": "section",
             "content": "", "section": heading, "level": level,
             "scope": scope, "line": line_no,
             "refs": {"decisions": [], "articles": []}, "confidence": "high"}
        concepts.append(c)
        return c

    cur, buf = None, []

    def flush():
        if cur is not None:
            cur["content"] = "\n".join(buf).strip("\n")

    for i, raw in enumerate(md_text.splitlines(), 1):
        m = _MD_HEADING.match(raw)
        if m:
            flush()
            cur, buf = new_section(m.group(2).strip(), len(m.group(1)), i), []
            continue
        if cur is None:
            if not raw.strip():
                continue
            cur, buf = new_section(None, 0, i), []
        buf.append(raw)
        for d in _DECISION_REF.findall(raw):
            if d not in cur["refs"]["decisions"]:
                cur["refs"]["decisions"].append(d)
        for a in _BRACKET_REF.findall(raw):
            if a not in cur["refs"]["articles"]:
                cur["refs"]["articles"].append(a)
    flush()
    return {"concepts": concepts, "flags": []}


PARSERS["markdown-sections"] = parse_markdown_sections


# ── code-symbols:python (③ 바이브코딩의 S1 — 설계: code-symbols-adapter-design.md) ──
# 계약은 위 어댑터들과 **같은 SourceConcept**다. 다른 건 "무엇이 단위인가"뿐:
_MD_CITE = re.compile(r"[a-z0-9][a-z0-9\-]*\.md")


def _signature(node, lines):
    """시그니처 = **원문 슬라이스**(`def ...:` 헤더 줄 그대로). 재구성하지 않는다.

    ★`ast`에서 인자를 되짜 맞추면 기본값 표현이 원문과 달라진다(`fmt=None` vs `fmt=`).
    그건 조각 본문으로 들어가는 값이라, 원문에 없는 문자열을 정본에 싣는 셈이다 —
    이 프로젝트가 조항·화면 파서에서 일관되게 지켜온 "원문 무수정"과 어긋난다.
    여러 줄 시그니처는 한 줄로 접되(공백 정규화) 토큰은 그대로 둔다."""
    end = node.body[0].lineno - 1 if node.body else node.lineno
    header = " ".join(l.strip() for l in lines[node.lineno - 1:max(end, node.lineno)])
    return re.sub(r"\s+", " ", header).strip()


_SKIP_COMMENT = re.compile(r"^#!|^#\s*-\*-|^#\s*coding[:=]")


def _comments_by_line(src_text):
    """줄번호 → 주석 원문. 셔뱅·인코딩 선언은 본문이 아니라 도구 지시라 뺀다."""
    import io
    import tokenize
    out = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src_text).readline):
            if tok.type == tokenize.COMMENT:
                s = tok.string.strip()
                if not _SKIP_COMMENT.match(s):
                    out[tok.start[0]] = s
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass                                   # 파싱은 ast가 판정한다 — 여기선 조용히 포기
    return out


def parse_code_symbols(src_text, scope=None, module=None):
    """파이썬 소스 → 심볼 단위 SourceConcept. 결정론(`ast`)·LLM 0·원문 무수정.

    ★`content`는 docstring 원문 그대로다. 왕복 게이트가 quote를 원문에서 찾으므로
    가공하면 귀속이 통째로 떨어진다(조항 파서가 조항 본문을 그대로 담는 것과 동형).
    시그니처는 `content`가 아니라 `fields.signature`에 둔다 — 조각 키가
    `<anchor>|<필드>`라서 겹치면 같은 지식이 두 조각으로 중복된다.

    ★비공개 심볼(`_`로 시작)도 걷는다. 공개 API만 보면 엔진 내부가 통째로 사라지는데,
    이 코퍼스에서 지식은 대부분 내부에 있다.
    """
    mod = module or "?"
    lines = src_text.splitlines()
    try:
        tree = ast.parse(src_text)
    except SyntaxError as e:
        # 깨진 파일 하나가 스냅샷 전체를 죽이면 안 되고, 조용히 삼켜서도 안 된다
        # (`|| exit 0`으로 실패를 감춘 resnapshot 전례 — 서 두 번 물렸다).
        return {"concepts": [], "flags": [f"구문 오류로 건너뜀: {e.msg} (line {e.lineno})"]}

    concepts = []
    comments = _comments_by_line(src_text)
    owner = {}                                    # 줄번호 → (범위 크기, anchor)

    def claim(anchor, start, end):
        span = (end or start) - start
        for ln in range(start, (end or start) + 1):
            if ln in comments and (ln not in owner or span < owner[ln][0]):
                owner[ln] = (span, anchor)

    def emit(anchor, kind, doc, line, section, signature=None):
        c = {"anchor": anchor, "kind": kind, "content": (doc or "").strip(),
             "section": section, "scope": scope, "line": line,
             "refs": {"decisions": [], "articles": [], "docs": []},
             "fields": {}, "confidence": "high"}
        if signature:
            c["fields"]["signature"] = signature
        text = doc or ""
        for d in _DECISION_REF.findall(text):
            if d not in c["refs"]["decisions"]:
                c["refs"]["decisions"].append(d)
        for a in _BRACKET_REF.findall(text):
            if a not in c["refs"]["articles"]:
                c["refs"]["articles"].append(a)
        # 코드→설계문서 인용. 실측 6%로 얇아서 **축이 아니라 부가 신호**다
        # (축으로 세우면 잡은 "자기기록 인용" 결함의 거울상이 된다).
        for m in _MD_CITE.findall(text):
            if m not in c["refs"]["docs"]:
                c["refs"]["docs"].append(m)
        concepts.append(c)
        return c

    emit(mod, "module", ast.get_docstring(tree), 1, None)
    claim(mod, 1, len(lines))

    def walk(node, prefix):
        for n in node.body:
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            qual = f"{prefix}.{n.name}"
            claim(qual, n.lineno, getattr(n, "end_lineno", None) or n.lineno)
            if isinstance(n, ast.ClassDef):
                emit(qual, "class", ast.get_docstring(n), n.lineno, prefix)
                walk(n, qual)
            else:
                kind = "method" if prefix != mod else "function"
                emit(qual, kind, ast.get_docstring(n), n.lineno, prefix,
                     _signature(n, lines))

    walk(tree, mod)
    # 임자가 정해진 뒤에 붙인다 — 안쪽 심볼이 바깥 것을 빼앗는 순서라 사후 배분이다.
    by_anchor = {}
    for ln, (_, anchor) in sorted(owner.items()):
        by_anchor.setdefault(anchor, []).append(comments[ln])
    for c in concepts:
        got = by_anchor.get(c["anchor"])
        if got:
            c["fields"]["comments"] = "\n".join(got)
    return {"concepts": concepts, "flags": []}


PARSERS["code-symbols:python"] = parse_code_symbols


# ── code-symbols:typescript (③의 두 번째 언어 — 설계 §6 "언어 복수") ──────
# ★파서 의존 0: `ast`는 파이썬 전용이고 tsc·node를 들이면 stdlib-only 관례가 깨진다.
# ★범위는 **다음 최상위 선언 전까지**로 근사한다 — 중괄호를 세지 않는다. 문자열·주석
# 안의 괄호까지 정확히 세려면 사실상 파서라, 근사임을 밝히고 근사로 둔다.
_TS_EXPORT = re.compile(
    r"^(export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(function|class|interface|type|const|let|var|enum)\s+([A-Za-z_$][\w$]*)")

# 본문층 — 호출 연쇄. 문자열·주석은 먼저 지운 뒤 찾는다(오탐 억제).
# `new Date().toISOString().split('T')` 같은 연쇄가 통째로 잡혀야 진단이 된다:
# 이름만(`toISOString`) 모으면 "UTC를 쓴다"는 사실이 안 보인다.
_TS_CALL = re.compile(
    r"(?:new\s+)?[A-Za-z_$][\w$]*\s*\([^()\n]*\)"
    r"(?:\s*\.\s*[A-Za-z_$][\w$]*\s*(?:\([^()\n]*\))?)*"
    r"|[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)+\s*\([^()\n]*\)")
_TS_STRING = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"|`[^`\n]*`")
_TS_STRIP_COMMENT = re.compile(r"//.*$")


def _ts_mask(line):
    """문자열·줄 주석을 **길이를 보존한 채** 가린다."""
    masked = _TS_STRIP_COMMENT.sub(lambda m: " " * len(m.group(0)), line)
    return _TS_STRING.sub(lambda m: m.group(0)[0] + "x" * (len(m.group(0)) - 2)
                          + m.group(0)[-1], masked)
_TS_JSDOC_END = re.compile(r"\*/\s*$")
_TS_LINE_COMMENT = re.compile(r"^\s*//\s?(.*)$")
_TS_DECISION = re.compile(r"DECISIONS?\s+\d{3,4}")
_TS_PLANNING = re.compile(r"planning/[\w./-]+")

#: TS/TSX의 kind 매핑 — 선언 키워드가 곧 kind다(유도하지 않고 표면을 그대로 쓴다).
_TS_KIND = {"function": "function", "class": "class", "interface": "interface",
            "type": "type", "const": "const", "let": "const", "var": "const",
            "enum": "enum"}


def _ts_jsdoc_above(lines, idx):
    """선언 바로 위 JSDoc 블록 → 본문. 없으면 빈 문자열. 원문 무수정(마커만 벗긴다)."""
    j = idx - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    if j < 0 or not _TS_JSDOC_END.search(lines[j]):
        return "", idx
    end = j
    while j >= 0 and "/**" not in lines[j]:
        j -= 1
    if j < 0:
        return "", idx
    body = []
    for l in lines[j:end + 1]:
        s = l.strip()
        s = re.sub(r"^/\*\*+", "", s)
        s = re.sub(r"\*/$", "", s)
        s = re.sub(r"^\*\s?", "", s)
        if s.strip():
            body.append(s.rstrip())
    return "\n".join(body).strip(), j


def parse_code_symbols_ts(src_text, scope=None, module=None):
    """TS/TSX 소스 → 심볼 단위 SourceConcept. 결정론·LLM 0·원문 무수정.

    파이썬 어댑터와 **같은 계약**이다(anchor·kind·content·fields·refs·line).
    다른 점 둘:
      · 범위를 근사한다(위 참조).
      · `refs`가 실제로 찬다 — 이 계열 코드는 기획 문서를 인용한다
        (`DECISIONS 0008`·`planning/40`). 파이썬 코퍼스에선 비어 있던 축이다.
    """
    mod = module or "?"
    lines = src_text.splitlines()
    decls = []
    for i, line in enumerate(lines):
        m = _TS_EXPORT.match(line)
        if m:
            decls.append((i, _TS_KIND.get(m.group(2), m.group(2)), m.group(3),
                          bool(m.group(1))))

    concepts = []

    def emit(anchor, kind, content, line, section, start, end, signature=None,
             exported=None):
        c = {"anchor": anchor, "kind": kind, "content": (content or "").strip(),
             "section": section, "scope": scope, "line": line + 1,
             "refs": {"decisions": [], "articles": [], "docs": []},
             "fields": {}, "confidence": "high"}
        if signature:
            c["fields"]["signature"] = signature
        if exported is not None:
            c["fields"]["exported"] = "true" if exported else "false"
        cmts = []
        for l in lines[start:end]:
            cm = _TS_LINE_COMMENT.match(l)
            if cm and cm.group(1).strip():
                cmts.append(l.strip())
        if cmts:
            c["fields"]["comments"] = "\n".join(cmts)
        calls = set()
        for l in lines[start:end]:
            for m in _TS_CALL.finditer(_ts_mask(l)):
                t = " ".join(l[m.start():m.end()].split())   # 자르는 건 **원문**
                if not t:
                    continue
                head = t.split("(")[0]
                calls.add(t if ("." in head or re.search(r"\)\s*\.", t)) else head.strip())
        if calls:
            c["fields"]["calls"] = "\n".join(sorted(calls))
        blob = "\n".join([c["content"], c["fields"].get("comments", "")])
        for d in _TS_DECISION.findall(blob):
            if d not in c["refs"]["decisions"]:
                c["refs"]["decisions"].append(d)
        for p in _TS_PLANNING.findall(blob):
            if p not in c["refs"]["docs"]:
                c["refs"]["docs"].append(p)
        concepts.append(c)

    # 모듈 본문 = 파일 머리의 JSDoc. 첫 선언이 자기 JSDoc을 가져가므로 겹치지 않는다.
    first = decls[0][0] if decls else len(lines)
    head_doc, head_start = "", first
    if decls:
        _, head_start = _ts_jsdoc_above(lines, first)
    lead = []
    for l in lines[:head_start]:
        s = l.strip()
        if s.startswith(("/**", "*", "*/")):
            s = re.sub(r"^/\*\*+|\*/$", "", s)
            s = re.sub(r"^\*\s?", "", s).strip()
            if s:
                lead.append(s)
    emit(mod, "module", "\n".join(lead), 0, None, 0, head_start)

    for n, (i, kind, name, exported) in enumerate(decls):
        end = decls[n + 1][0] if n + 1 < len(decls) else len(lines)
        doc, _ = _ts_jsdoc_above(lines, i)
        emit(f"{mod}.{name}", kind, doc, i, mod, i, end, lines[i].strip(),
             exported=exported)
    return {"concepts": concepts, "flags": []}


PARSERS["code-symbols:typescript"] = parse_code_symbols_ts
