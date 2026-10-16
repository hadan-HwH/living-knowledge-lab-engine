# we-volley 베이스 — adjudication 펀치리스트 (owner 확인 대기)

> `ingest_wevolley.py`가 DECISIONS.md 22개를 `events.auto.yaml`로 추출했다. **제목 마커(`→ NNNN로 대체`)의 full-supersede만 신뢰**한다 — 아래는 추출기가 자동 처리하지 않은 관계로, 소유자(사용자) 확인 후 `events.adjudication.yaml`로 승격한다(§10 extractor→proposal→adjudication).

## 추출 충실도 결과 (이번 베이스의 핵심 발견)

| 관계 종류 | 추출기 | 예 |
|---|---|---|
| 제목 full-supersede | ✅ 자동 | 0004 → 0005 |
| 제목 partial-supersede | ⚠️ flag만 | 0009 ③ → 0010 |
| **본문 전용 supersede** | ❌ 놓침 | 0016 → 0010 (익명글 전제 붕괴) |
| 본문 전용 refine | ❌ 놓침 | 0015 → 0011 (DM 설계 확정) |

→ **semi-structured 마커는 관계의 일부만 담는다. 나머지는 산문에 있어 의미 추출·판단이 필요하다.** 이것이 Track E(자동 추출)의 상한을 보여주는 첫 실측이다.

## 확인 대기 항목

### A. 0009 ③ → 0010 (partial, disclosure 축)
- 문서: 0009 제목 "→ **③은 0010으로 대체**", 0010 본문 "0009 ③(AI 배지 공개)을 뒤집음".
- 0009는 ①(route guard)·②(anon RLS)·③(봇 공개 배지) 셋. 그중 **③만** 0010이 뒤집음(봇 노출 = 공개 → 비공개).
- **권장:** 축 분해(guide R6) — 새 sub-target `WV.T.bot_disclosure`에 `o0009_public` → `o0010_private` supersede. 0009의 ①② 부분은 `WV.T.0009`에 active로 유지.

### B. 0016 → 0010 (본문 전용, seeding-style 축)
- 문서: 0016 제목 "익명 글 전제 붕괴 대체", 본문 "로드맵 §6의 '익명 글 위주'는 0011의 is_anonymous 드롭으로 전제 붕괴 → 전원 네임드 페르소나로 대체".
- 0010의 **"익명 글 위주" 시딩 방식**을 0016이 "전원 네임드"로 뒤집음. 단 0010의 `allow_dm`·비공개 disclosure는 0016이 유지.
- **권장:** 축 분해 — sub-target `WV.T.bot_seeding_style`에 `o0010_anon` → `o0016_named` supersede. reason_type = `constraint_change`(is_anonymous 드롭이 전제 붕괴).

### C. 0015 → 0011 (본문 전용, refinement)
- 문서: 0015 "0011의 '한 id=2 프로필' DM 설계를 확정 구현안으로".
- 권위 변화 없음 — 0011 결정을 구체화. `authority_delta_kind = refinement`.
- **권장:** A 변경 없음(no-op). `WV.T.0011` active 유지, 0015는 구현 상세로 링크만.

## 남은 층 (feature scope)

DECISIONS.md 22개는 **프로젝트 전역 scope**. `planning/작업완료/*.md` ~50개 플랜 안의 D-N(예: "59 D2 typing indicator 기각")은 **feature scope**로, 필요 시 `scope: wevolley/<plan>`으로 별도 ingest한다. reversal 실사례(59 D2 add→기각+revert)가 여기 많다.
