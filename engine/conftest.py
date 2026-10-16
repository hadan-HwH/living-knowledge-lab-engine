"""테스트 공용 — 데이터 품질 게이트의 전제 확인.

★소유자 질문: "나는 제너릭한 엔진을 연구하는데 왜 fixture가 없으면 안 되는 애가 됐지?"
재보니 **엔진은 이미 제너릭했다** — 픽스처를 통째로 없애도 대부분이 통과한다.
틀린 건 어시스턴트의 진단이었고, 그 진단이 더 나쁜 걸 가리고 있었다.

    for corpus in sorted(cp.discover_corpora()):   # 데이터 0이면 [] → 루프 본문 0회
        ...                                        # → 검사 0건인데 **PASSED**"""
import corpus as cp


def require_corpora(testcase):
    """데이터 품질 게이트의 전제 — 코퍼스가 없으면 통과가 아니라 skip."""
    names = sorted(cp.discover_corpora())
    if not names:
        testcase.skipTest("코퍼스 픽스처 0개 — 데이터 품질 게이트가 검사할 대상이 없다(통과 아님)")
    return names


def require_corpus(testcase, name):
    """특정 코퍼스를 이름으로 지목하는 게이트의 전제 — 없으면 통과가 아니라 skip."""
    if name not in set(cp.discover_corpora()):
        testcase.skipTest(f"코퍼스 `{name}` 없음 — 이 게이트가 검사할 대상이 없다(통과 아님)")
    return name


def require_checked(testcase, n, what):
    """게이트가 **실제로 몇 건을 봤는지**. 0이면 안 돈 것이라 skip.

    코퍼스가 있어도 그 안에 해당 자산(정본·스냅샷 등)이 없으면 같은 vacuous pass가 난다 —
    한 겹 더 막는다."""
    if not n:
        testcase.skipTest(f"{what} 0건 — 게이트가 검사한 대상이 없다(통과 아님)")
    return n
