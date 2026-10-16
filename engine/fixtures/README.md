# fixtures/ — 코퍼스별 데이터 구조 (2026-08-01 정리)

각 코퍼스(`acme-docs`·`personal-wevolley`·`lab-self`)는 성격별로 분리한다.
**"완성된 구조화 지식"과 "실험·검증 스캐폴딩"을 섞지 않는다** — L1을 깔끔하게 계속 추가하려는 목적.

```
<corpus>/
  l1-snapshots/   ★ 완성된 구조화 지식 (이게 L1의 산물)
                    <sha>/ = concepts·terms·relations·bodies·decisions-from-git·
                    concept-graph·evolution — 기계 생성·SHA 고정·재생성 가능
  gold/           벤치마크 gold 케이스 (손 저작 정답, events.yaml + expected.yaml)
  auto/           자동 추출 후보 (events.auto.yaml — "gold 아님", adjudication 대기)
  probes/         Tier B 탐침 실험 (lab-self)
  why/            사람 steering "왜" 층 (lab-self — 완성 구조화의 일부)
```

## 성격 구분

| 폴더 | 지위 | 신뢰도 |
|---|---|---|
| `l1-snapshots/` | **완성 구조화** — 우리가 만든 지식 산물 | 결정론·왕복 게이트 |
| `gold/` | 벤치마크 정답 — 손 검증 | 사람 저작 |
| `auto/` | 자동 추출 후보 | proposal (미검증) |
| `probes/` | 방법 실험 | 회차별 |

## 코드 참조 (경로 이동 시 갱신 대상)

- `registry.yaml` gold_events → `<corpus>/bench/<case>/events.yaml` (현행성 블록용 이벤트 원장 선언)
- `corpus.py` corpus_of → fixtures 첫 조각(깊이 무관)
- `corpus.py` `ledger_dir`·`canon_dir`·`work_dir`·`bench_dir` — 경로를 아는 곳은 여기 한 곳
