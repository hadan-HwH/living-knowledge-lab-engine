# 관계 어휘 판정 큐 — wevolley 미등록 7종 (소유자 대기)

> **어떻게 드러났나:** 2026-08-03 전수조사에서 **관계 어휘를 검증하는 코드가 하나도 없다**는
> 게 확인돼(`relation_canon`은 죽어 있었다) 등록 게이트를 신설했다. 그 게이트가 돌자마자
> 잡은 게 **이 세션의 wevolley 추출 자신**이다 — 계약(§2 `canonical` = canon-13 또는 등록
> 확장, 새 어휘는 `canonical: NEW` + `new_family` 제안)을 어기고 미등록 어휘를 그대로 썼다.
> 게이트가 없어서 그때는 아무도 몰랐다.
>
> **왜 자동으로 안 고치나:** 아래 매핑은 **의미 판정**이다. 기계가 "이건 사실
> `constrains`야"라고 정하면 계약이 금지한 지어냄과 같아진다. 소유자 판정 항목.

## 실측

| | 건수 |
|---|---|
| 등록 통과 | 565 |
| `NEW` 제안(계약이 허용한 절차) | 50 |
| **미등록(계약 위반)** | **19** — 전부 `personal-wevolley` |

## 판정 대상 7종

| 어휘 | 사용 | 잠정 읽기(근거: 사용 맥락) | 후보 처리 |
|---|---|---|---|
| `realized_by` | 10 | 개념 → 그것을 구현하는 스키마/컴포넌트 | core-13 `part_of` 역방향? 또는 확장 등록 |
| `depends_on` | 4 | 이 기능이 선행 조건을 요구 (notify() 선행 등) | 확장 등록 유력 — 선행 관계는 core-13에 없다 |
| `has_state` | 1 | 개념 → 상태집합(charge status 전이) | `part_of`로 접힐 수 있음 |
| `produces` | 1 | charge_plans → club_charges 생성 | core-13 `computes`의 동의어일 가능성 |
| `motivates` | 1 | 문제 진단 → 그 해법 | core-13 `enables`? 아니면 별도 |
| `impacts` | 1 | 개명이 launchd plist에 파급 | core-13 `constrains`? 아니면 영향 축 별도 |
| `supersedes` | 1 | 결정 대체 | **결정층 어휘와 충돌** — 개념층에서 쓸 것인지부터 판정 |

## 선택지

1. **확장 등록** — `canon-extensions.yaml`에 `family` + `meaning` + `status: candidate`로 추가.
   `depends_on`처럼 core-13에 대응이 없는 것은 이쪽이 자연스럽다.
2. **core-13으로 재매핑** — `produces`→`computes`처럼 동의어면 `canonicalize`의 synonyms에
   넣어 표면은 보존하고 정본만 수렴시킨다(어휘 증식 없음).
3. **`NEW` 제안으로 강등** — 판단 보류. 그 경우 관계는 원장에 남되 정본 편입에서 빠진다.

## 후속

`supersedes`는 결정층에서 이미 쓰는 어휘라, 개념층 관계로도 쓰면 같은 이름이 두 층에서
다른 뜻이 된다. 어휘 충돌 자체가 판정 대상이다.
