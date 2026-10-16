# engine/ — 구조화 파이프라인

> **공개본 안내.** 아래 `docs/…` 링크가 가리키는 설계·실험 문서와 비공개 문서 코퍼스·`lab-self` 데이터는
> 이 저장소에 포함되지 않는다. 동봉된 데모 코퍼스는 `fixtures/personal-wevolley`뿐이다.
> 테스트·주석에 나오는 `acme-docs` 코퍼스와 그 앱·조항·결정(`prime-commerce/…`, `INV-NN`, `D-NNNN` 등)은
> 전부 **가공한 예시**다.

진입점은 `structure_app.py` 하나다.

```
ingest → prep → [Tier B 추출] → fold → promote → brief | drift
```

| 단계 | 주체 | 산출 |
|---|---|---|
| ingest·l1_snapshot | 결정론 | `work/<app>/sections.yaml` · `canon/tier-a/<sha>.yaml` |
| prep | 결정론 | `canon-context.yaml`(S2용, 조항은 head 120자) · **`articles.yaml`(S3a용, 조항 전문)** · `extract-manifest.yaml` |
| **개념 추출·조항 귀속·관계·별칭** | **Tier B(LLM)** | `subconcepts` · `members` · `relations` · `aliases` |
| fold | 결정론 | `adjudication.yaml` (왕복 게이트·판정 큐) |
| promote | 결정론 | `canon/concepts.yaml` (정본 — 개념·현행·본문·별칭) |
| brief | 결정론 | 소비 경로. 기본은 '어떻게', `--why`로 이력 |
| metrics | 결정론 | `canon/metrics.yaml` (정본 지표 + 불변식 9 게이트) |
| drift | 결정론 | `canon/drift.yaml` (낡음·최신성) |
| **how · impact · recent** | 결정론 | **질의 3종** — 소비 경로 |

단계마다 **필요한 입력만** 준다 — 조항 전문은 S3a에만 준다(합치면 S2 입력이 몇 배로 커진다).
불변식 전체 목록은 [INVARIANTS.md](INVARIANTS.md). 봉인된 연구 자산은 `research/`.

## 재생과 게이트

```bash
scripts/regen.sh <corpus> [--snap SHA]     # 원장 → 정본 전량 재생 + 지표 + 게이트
```

**회차가 끝나면 이걸 돌린다.** 결정론·LLM 호출 0·멱등(같은 원장이면 diff 0).

절차 본체는 [`regen.py`](regen.py)에 있다(스크립트는 진입점만). **계획과 실행을 갈랐다** —
`regen_plan(apps)`가 "무엇을 어떤 범위로 도는가"를 데이터로 내고 `run_plan`이 그걸 실행한다.
종전엔 bash가 이 판단을 했고 테스트가 없어서, `crosscheck`에 알파벳 첫 앱 하나만 넘기는
결함이 살아 있었다. 엔진 함수는 지키면서 그걸 **부르는 층**은 안 재던 구멍이다.

★왜 만들었나: 본문 층을 만들고도 **산출물을 커밋하지 않아**, 엔진이 만들 수 있는 본문과
커밋된 정본 본문이 크게 벌어진 채 게이트가 전부 초록이었다. 코드 게이트(pytest·LOC·도달률)는
"기계가 할 수 있나"를 재지 "정본이 그렇게 됐나"를 안 잰다.

| 불변식 | 무엇을 막나 | 어디 |
|---|---|---|
| **8 anchor 유일성** | 같은 anchor 2개 = 정체성 붕괴. **총량 게이트로는 영원히 안 잡힌다**(중복은 늘어나는 방향) | `anchor_uniqueness_report` |
| **9 정본 단조** | 개념·관계·본문·현행이 회차를 거치며 줄지 않는다(은퇴는 기록에 근거해 면제) | `metrics_gate` |

불변식 **4(재현성)는 자동**이다 — `regen.sh`가 재생 후 한 번 더 접어 대조한다
(`reproducibility_report`, `byte_identical`).

### ★조용한 미실행 금지

**게이트가 조건 불충족으로 안 돌면 `skipped(사유)`를 남긴다.** 없는 키로 두지 않는다.

감사에서 게이트 여러 개가 **조용히 꺼진 채 몇 세션을 버틴 것**이 드러났다. fixture 재편이
경로를 바꿨는데 배선이 따라오지 않은 경우가 대부분이었고, 공통점은 **꺼졌다는 사실이 아무 데도
안 남는다**는 것이었다. 그 관례를 전부에 폈다.

지금 남는 자리: `adjudication.yaml`의 `stats.relation_vocab`, 정본 `meta.skipped`
(`body_assembly`·`fragment_tombstone`·`last_seen`·`current_plane`), promote 출력의 `미실행 [...]`,
regen 출력의 `⚠ 침식 감시 미실행: <사유>`.

**최신성은 유도하지 않고 기록을 읽는다.** 스냅샷의 `meta.generated_at`을 `newest_snapshot()`이 쓴다.
날짜 없는 스냅샷은 순위에 넣지 않고 `undated`로 보고하며, 하나라도 있으면 `fresh=False`다
(모르는 것을 통과라 부르지 않는다).

**상태 문서에 적는 정본 숫자는 `canon/metrics.yaml`에서만 인용한다** — 기억이 아니라 파일이 근거가 되게.

### 층간 대조 — `crosscheck`

```bash
python3 structure_app.py crosscheck <corpus> [앱] [--scope S]
```

**같은 개념 아래 조항과 화면이 다른 값을 말하는가.** 한 개념에 서로 다른 층의 조각이 모였고,
같은 항목에 값이 다르면 후보다.

★**기계는 판정하지 않는다.** 어느 쪽이 맞는지는 정책·화면 담당자의 몫이고, 검출기는
원문을 나란히 보여주는 데까지만 한다. 단위 환산(2시간 vs 120분)도 안 맞춘다 — 맞추려
들면 지어내는 셈이다.

★**값 비교는 숫자 집합으로 한다.** 층마다 표 컬럼 구조가 다르기 때문이다(가공 예시):

```
조항  | Checkout step timeout | 7분 | 2–12분 | 설명 |     (기본값·범위·설명)
화면  | **Checkout step timeout** * | 분 | 7 | 2–12분 |   (구성·기본값·범위)
```

문자열로 비교하면 다르지만 말하는 값은 같다(7·2·12). 문자열 비교로 처음 돌렸을 때 후보 대부분이
이런 오탐이었고, 오탐이 많으면 사람이 목록을 안 본다(게이트가 죽는 경로).

★**한계(정직성):** 표 밖의 산문 불일치(부등호 역전·오인용 등)는 못 잡는다 — 여전히 사람 몫이다.

### 회차와 낡음 감시

`regen.sh`가 재생 **전에** 직전 정본을 `ledger/rounds/round-NNNN.yaml`로 남긴다.
그게 S6 `drift`의 `prev`다.

- **회차 = 내용이 바뀐 재생.** 재현성 검사가 매 재생마다 promote를 한 번 더 돌리므로
  실행 횟수로 세면 회차가 뻥튀기된다. 직전 회차와 내용이 같으면 아카이브하지 않는다.
- **drift는 현행 평면만 비교한다.** 옛 텍스트를 이력으로 남기므로, 이력까지 섞으면
  "옛 텍스트가 아직 있다"로 읽혀 **변화가 상쇄된다**.
- 회차 원장이 없으면 **비교 대상이 없다고 말한다** — 조용히 자기 자신과 비교해
  "변화 없음"으로 읽히게 두지 않는다.

### 엔진 자립 — 데이터 없이도 도는가

코퍼스를 장착하지 않아도 엔진 테스트는 합성 데이터로 전부 돈다. 코퍼스를 순회하는
**데이터 품질 게이트**는 대상이 없으면 **skip + 사유**다.

★**검사 대상 0건은 통과가 아니라 skip이다.** `for corpus in []`이면 루프 본문이 0회 도는데
초록불이 켜진다 — "조용한 미실행"을 테스트 층에서 재생산하는 셈이다.
`conftest.require_corpora` / `require_corpus` / `require_checked`를 거치게 하고,
새로 쓰는 게이트도 강제되도록 `test_gate_vacuity.py`가 소스를 훑어 가드 누락을 잡는다.

### 질의 3종

```bash
python3 structure_app.py how    <corpus> <개념 이름|anchor> [--why]
python3 structure_app.py impact <corpus> <조항 ID|개념 anchor>
python3 structure_app.py recent <corpus> [앱]
```

읽기 전용·결정론·LLM 0.

| 질의 | 무엇 | 대응하는 원칙 |
|---|---|---|
| `how` | 이 개념은 **지금** 어떻게 동작하나 — 현행 조각·현행 결정·별칭·출처 조항 | 현재만 본다(이력은 `--why`로만) |
| `impact` | 이 조항을 바꾸면 무엇이 흔들리나 — 직접 인용 + 관계 1홉 | 조항이 정확해야 비교가 된다 |
| `recent` | 최근 무엇이 이력으로 내려갔나 — 갱신(superseded)·소멸(removed)·결정 변경 | 결정은 계속 바뀐다 |

★**결정은 문서 표기로 읽힌다.** 자기참조 토큰(`o_<ID>`)이 아니라 원장 `source`의 문서 표기
(`INV-D-8812 (이력: INV-D-7318)` 같은 꼴)로 나온다.

★**없으면 없다고 말한다.** 빈 결과를 빈 화면으로 내면 "본 적 없다"와 "봤는데 없다"가
구분되지 않는다 — 세 질의 전부 `note`를 낸다.

### registry 선언 두 축 (헷갈리기 쉬움)

| 선언 | 무엇 | 쓰는 곳 |
|---|---|---|
| `app_scopes` | 작업 폴더 → **정본 scope**(`prime-commerce/mango/mango`) | promote |
| `work_scopes` | 작업 폴더 → **sid 접두**(`mango`) | fold |
| `canon_snap` | 코퍼스가 보는 시점 | regen 기본 `--snap` |

보통 셋 다 폴더 이름과 같아 선언이 필요 없다. 회차 폴더(`mango-pipeline-r1`)만
**양쪽 축 모두** 폴더 이름과 다르다(원장 sid가 `mango#`) — 미선언이면 fold가 배치를 통째로 막는다.
`canon_snap`을 선언으로 두는 이유: "최신 스냅샷"을 `sorted()[-1]`로 고르면 SHA
알파벳 정렬이 시간 순이 아니라 언제든 조용히 틀린다.

## 결정 원장 — A-reducer + S축(O2)

결정을 문서가 아니라 **이벤트 원장**으로 다룬다. **권위축(A)** 과 **근거축(S)** 을 기계로 계산하는
최소 구현이다. 사람이 annotation 규칙으로 만든 gold event 원장을 입력받아
"지금 공식적으로 유효한 결정"과 "그 근거 상태"를 재생한다.

- **A축:** DecisionAct fold → authority projection. **S축:** EvidenceEvent fold → 독립성 그룹 기반
  `unknown|supported|mixed|challenged`(동결 규칙). ImplementationObservation은 로드하되 무시한다.
- **S는 A를 절대 변경하지 않는다** — supported+revoked, mixed+active가 공존한다.
- 점수(`S=0.72`)·trend·온톨로지·자동 전이 없음. 전이 계약과 불변식만.

| 파일 | 역할 |
|---|---|
| `reducer.py` | `project_authority(events, target, valid_at, known_at, scope)` — bitemporal 필터 + dedup + fold + 충돌 감지 + scope-exception |
| `evidence.py` | `evidence_profile(events, subject, valid_at, known_at)` — EvidenceEvent fold, 독립성 그룹 dedup, 동결 label 규칙 |
| `queries.py` | `current_authority`, `option_evidence_profile`, `history_rationale`, `open_decisions` |
| `corpus.py` / `ingest.py` | 경계 위계(corpus>tier>platform>app)·구조 발견 (registry 데이터 구동) |
| `parsers.py` | Tier A 형식 어댑터 — 결정 로그 표 → 결정 스켈레톤(+`content` 원문)+supersede 관계, 마크다운·코드 어댑터 |
| `map_events.py` | 스켈레톤 → 후보 event 매핑. target/option은 anchor placeholder(`confidence: proposal`), 못 정하는 건 flag |
| `extract.py` | discover→parse→map 결합 드라이버 → 제안 원장 |
| `fixtures/<corpus>/bench/<case>/` | gold event 원장(`events.yaml`) + 질의별 정답(`expected.yaml`) |
| `test_reducer.py` | 장착된 모든 fixture의 gold 질의를 재생·대조 + 멱등성 |

```bash
cd engine && python3 test_reducer.py     # 평문 러너 (pyyaml만 필요)
python3 -m pytest -q                      # pytest
```

### 동봉된 gold — we-volley

- **wevolley-decisions** — clean supersede(0004→0005) + partial supersede(0009③→0010) 축분해
- **wevolley-plan59** — feature scope. ★**revoke**(typing indicator: 구현→기각→git revert = 죽은 결정,
  current=none, supersede와 구별) + 유지 결정(메시지 삭제)

`ingest_wevolley.py`(Track-E-lite)가 DECISIONS.md 22 결정 → `events.auto.yaml`. 현재권위 투영 =
**21 active + 0004→0005**. 본문 관계는 `events.adjudication.yaml`(relation overlay, A-reducer 무시)·
`ADJUDICATION.md`. **추출 충실도: 제목 마커만 신뢰, 본문 supersede·partial은 adjudication 필요.**

reducer는 그 밖에 번복과 이중시간(현재 / 과거효력+현재지식 / 과거 transaction cutoff),
clarification(`confirm_current`은 권위 불변), scope **exception**(`exception_to` 선언 — 예외 공존은
충돌이 아님), **재채택**(supersede with 과거 option successor — 상태 왕복 active→superseded→active)을
구현한다. 이 유형들의 gold 원장은 비공개 코퍼스에 있어 공개본에는 없다 — 공개본에서는 we-volley
gold 2건과 합성 재채택 원장(`test_term_layer.py`)이 돈다.

### 구현된 불변식 (reducer)

멱등성 · 이중시간 안전성(`recorded_at > known_at` 불가시, `valid_at > 질의시점` 미효력) ·
scope 보존(계층 prefix 매칭) · 충돌 가시성(비호환 active >1 → `authority_conflict`, 임의 승자 없음) ·
권위 우선(하위 authority가 상위 active를 못 뒤엎음).

**scope-exception 의미론:** `exception_to`가 선언된 active option은 일반 option이 active인 동안
충돌이 아니라 scoped override다. 질의 scope를 지배하는 가장 구체적인 예외가 이기고, 밖에서는
일반이 current이며 `exceptions` 맵으로 예외 존재가 노출된다. reducer는 scope 모양만으로 예외를
추론하지 않는다(annotator 선언 필수).

### 아직 아닌 것

- **부분 scope supersede**(같은 option의 일부 scope만): 현재는 축별 target 분해 + relation overlay로 흡수.
- `re_adopt` **전이**(무현행 부활): 전이는 구현됐으나 자연 gold 없음 — 현행을 밀어내는 재채택은
  supersede(successor=과거 option)로 표현한다. 남은 것은 rejected/revoked에서 현행 없이 부활하는 케이스.
- **exception의 해제**(예외·일반의 supersede 시 예외의 운명): 자연 사례·의미론 둘 다 미정.
- `amend`/`narrow_scope`/`expand_scope`: A-state 무변경(successor option + supersede로 표현해야 함).
- S축 trend·proposition subject·`depends_on` 합성 — gold가 요구할 때만.
- I(구현)·H(건강도) 축 — 다음 단계.
