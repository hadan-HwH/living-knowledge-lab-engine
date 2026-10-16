"""용어 정형화 양방향 검출 — scope/sense를 살려 모으기(동의어)와 가르기(동형이의) 둘 다.

소유자(2026-08-01): 어휘는 반대 두 방향으로 깨진다 — 표면만 보면 반드시 한쪽 필패.
  · 동의어(synonymy):  여러 표면 → 한 sense  = **merge 제안** (Partition = store/branch/project)
  · 동형이의(homonymy): 한 표면 → 여러 sense = **split 경고** (role = 직원role@console-builder vs 할인role@inv)
어시스턴트 ②오답 = 동형이의를 동의어로 병합(표면 "role"만 봄). 근본 교정 = member에 sense를
달고 **sense-일치를 게이트**로 삼음. 그래프 데이터는 이미 scope를 달고 있어 가르기가 거의 공짜.

게이트(전부 결정론):
  공통: provenance 왕복(각 quote가 해당 앱 문서에 실재) · ≥2 앱(단일 앱은 분기 아님).
  synonym(merge): ≥2 표면 · **sense 1종**(불일치면 = 동형이의 오병합 → 거부).
  homonym(split): ≥2 sense · 표면 1종(여러 표면이면 동형이의 아님).
"""
from __future__ import annotations


def verify_divergence(findings, app_text):
    """findings: [{kind:"synonym"|"homonym", canonical?/surface?, members:[{app,surface,sense,quote}]}].
    app_text: {app: 문서 텍스트}. merges(동의어 병합)·splits(동형이의 분리)로 분류."""
    merges, splits, rejected = [], [], []
    for f in findings:
        members = f.get("members", [])
        kind = f.get("kind")
        apps = {m.get("app") for m in members}
        surfaces = {m.get("surface") for m in members}
        senses = {m.get("sense") for m in members}
        bad = [m for m in members
               if (m.get("quote", "") or "") not in app_text.get(m.get("app"), "")]
        if bad:
            rejected.append({**f, "reason": f"provenance 실패 {[m.get('app') for m in bad]}"})
        elif len(apps) < 2:
            rejected.append({**f, "reason": "단일 앱(분기 아님)"})
        elif kind == "synonym":
            if len(surfaces) < 2:
                rejected.append({**f, "reason": "표면 1종(이미 통일)"})
            elif len(senses) > 1:                       # ★②의 자동 방지
                rejected.append({**f, "reason": f"sense 불일치(동형이의를 병합 시도): {sorted(senses)}"})
            else:
                merges.append(f)
        elif kind == "homonym":
            if len(senses) < 2:
                rejected.append({**f, "reason": "sense 1종(이미 통일 — 동형이의 아님)"})
            elif len(surfaces) > 1:
                rejected.append({**f, "reason": "표면 여러 종(동형이의는 같은 표면이어야)"})
            else:
                splits.append(f)
        else:
            rejected.append({**f, "reason": f"kind 불명 '{kind}'"})
    return {"merges": merges, "splits": splits, "rejected": rejected,
            "stats": {"n": len(findings), "merges": len(merges),
                      "splits": len(splits), "rejected": len(rejected)}}
