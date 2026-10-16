#!/bin/bash
# 추가 코퍼스 장착 — 저장소 밖 데이터 디렉터리의 코퍼스를 engine/fixtures/ 아래에 심링크로 붙인다.
#
# 이 저장소에는 데모 코퍼스(`personal-wevolley`)가 실체로 들어 있다. 그 밖의 코퍼스
# (예: lab-self)는 데이터를 별도로 두고 이 스크립트로 장착한다. 장착하지 않으면
# 해당 코퍼스에 의존하는 테스트는 **사유와 함께 skip**된다(실패가 아니다).
#
# usage: scripts/mount-data.sh <데이터_경로>      (데이터_경로/fixtures/<corpus>/ 구조)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${1:-}"

if [ -z "$DATA" ] || [ ! -d "$DATA/fixtures" ]; then
  echo "usage: scripts/mount-data.sh <데이터_경로>   (<데이터_경로>/fixtures/<corpus>/ 가 있어야 한다)"
  echo "  → 장착 없이도 pytest는 초록이다(데이터 의존 테스트는 사유 skip)."
  exit 0
fi

echo "데이터 장착: $DATA"
FAIL=0
mkdir -p "$ROOT/engine/fixtures"
for src in "$DATA"/fixtures/*/; do
  c="$(basename "$src")"
  dst="$ROOT/engine/fixtures/$c"
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then
    echo "  – $c — 이미 실체가 있다(저장소 동봉 데이터). 건너뜀"
    continue
  fi
  ln -sfn "${src%/}" "$dst" && echo "  ✓ engine/fixtures/$c → ${src%/}" || FAIL=1
done
exit $FAIL
