#!/bin/bash
# lab 최신성 — 세션이 끝나면 lab 자신의 Tier A 스냅샷을 현재 HEAD로 재생성한다.
# 실시간이 아니라 세션 단위(정직성 게이트 §4-5). 결정론·LLM 0·멱등(같은 HEAD면 diff 0).
#
# 2026-08-04 재작성: 종전 스크립트는 아카이브된 모듈 4개(snapshot_pipeline·git_spine·
# lab_evolution·lab_concept_graph)와 옛 경로(l1-snapshots/)를 불렀고, 전부 `|| exit 0`으로
# 감싸여 있어 **조용히 아무것도 안 하고 성공한 척**했다. 이 프로젝트가 반복해서 당한
# 패턴이라(본문 소실·증발 432건) 실패를 삼키지 않고 찍는다.
set -uo pipefail

ENGINE="$(cd "$(dirname "$0")/../engine" && pwd)"
cd "$ENGINE" || { echo "resnapshot: engine 경로 없음" >&2; exit 0; }

SHA=$(git rev-parse --short HEAD 2>/dev/null) || { echo "resnapshot: git 아님" >&2; exit 0; }

# ① Tier A 스냅샷(현재 HEAD) → canon/tier-a/<sha>.yaml — 최신성 gap 0
python3 l1_snapshot.py lab-self >/dev/null 2>&1 \
    || echo "resnapshot: l1_snapshot 실패 (lab-self @ $SHA)" >&2

# ② 낡음·최신성 리포트 → canon/drift.yaml — 정본이 뒤처지면 여기서 드러난다
python3 structure_app.py drift lab-self lab >/dev/null 2>&1 \
    || echo "resnapshot: drift 실패 (lab-self @ $SHA)" >&2

exit 0
