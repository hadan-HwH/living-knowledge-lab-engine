#!/bin/bash
# 정본 재생 — 원장(work/<app>)에서 정본(canon/concepts.yaml)을 처음부터 다시 만든다.
# 결정론·LLM 호출 0·멱등(같은 원장이면 diff 0). 회차마다 이걸 돌리는 게 규약이다.
#
# ★2026-08-07: 절차 본체를 `engine/regen.py`로 옮겼다. 이 파일은 진입점만 남긴다.
#
# 왜 옮겼나 — 세션 15의 성공 측정이 0/3이었고, 원인이 여기 있던 이 한 줄이었다:
#
#     structure_app.py crosscheck "$CORPUS" "$(basename "$(ls -d "$WORK"/*/ | head -1)")"
#
# **알파벳 첫 작업 폴더 하나**를 골라 넘겨, 개념 일부만 대조하고 있었다.
# 엔진 함수는 테스트 천여 개가 지키는데 그것들을 **어떤 범위로 부를지** 정하는
# 이 bash 층에는 테스트가 하나도 없었다 — "게이트 전부 초록인데 결함이 살아 있었다"의
# 4번째 계열이고, 이번엔 결함이 게이트가 아니라 게이트를 부르는 층에 살았다.
# 이제 계획이 데이터고(`regen_plan`), 계획에 게이트가 걸린다(`engine/test_regen.py`).
#
# usage: scripts/regen.sh <corpus> [--snap SHA]
#        snap 미지정 시 registry의 canon_snap 선언을 쓴다(유도하지 않는다).
set -uo pipefail

ENGINE="$(cd "$(dirname "$0")/../engine" && pwd)"
cd "$ENGINE" || { echo "regen: engine 경로 없음" >&2; exit 1; }
exec python3 regen.py "$@"
