#!/usr/bin/env python3
"""베이스라인 — 기존 78단어 사전을 **같은 테스트셋**에 적용한다.

── 왜 베이스라인부터 만드나 ──────────────────────────────────────────────
신경망 정확도 하나만 보면 그게 좋은 건지 알 수 없다. 비교 대상이 둘 필요하다.

  1. **무작위/최빈** — 3분위라 33.3%. 이보다 못하면 학습이 안 된 것이다
  2. **기존 사전** — 실제로 운용 중인 규칙. **이걸 못 이기면 교체할 이유가 없다**

2번이 진짜 기준선이다. 트랜스포머가 사전을 못 이기면 "딥러닝이 안 통하는
문제"라는 결론이 나오는 것이고, 그것도 결과다 — 숨기면 안 된다.

── 사전을 3분류로 바꾸는 법 ─────────────────────────────────────────────
사전은 정수 점수(-3 ~ +3)를 낸다. 이걸 상/중/하로 자를 경계가 필요한데,
**훈련셋에서 라벨 분포에 맞춰 고른다** — 테스트셋을 보고 고르면 사전 쪽에
부당한 이득을 준다(그것도 누수다). 모델과 똑같은 규칙을 적용해야 공정하다.
"""
import numpy as np

import bridge
from data import LABELS, load, make_labels, split

# 🔴 사전 점수는 **운영 중인 score_text 를 그대로** 부른다(§bridge.py).
# 복사본을 쓰면 "예전에 복사해둔 사전"을 이기는 것이지, 지금 돌고 있는 그것을
# 이기는 게 아니다. 서브프로세스라 느리니 한 번에 몰아서 부른다.
_cache = {}


def scores(rows):
    todo = [r["title"] for r in rows if r["title"] not in _cache]
    if todo:
        for t, (sc, hits) in zip(todo, bridge.score_titles(todo)):
            _cache[t] = (sc, hits)
    return [_cache[r["title"]] for r in rows]


def fit_thresholds(rows):
    """훈련셋 점수의 3분위로 경계를 정한다.

    🔴 **매칭이 0개인 헤드라인은 빼고** 분위수를 구한다. 첫 실행에서 이걸 안 했다가
    경계가 +0.0/+0.0 으로 잡혔다 — 테스트셋의 80.9% 가 매칭 0개라 점수가 0 이고,
    그러면 `s <= lo` 가 먼저 걸려 **그 81% 가 전부 '하락'으로 찍힌다.** 정확도가
    29.6% 로 무작위(33.3%)보다 낮게 나왔는데, 그건 사전이 나빠서가 아니라
    **내가 사전을 불공정하게 번역해서**였다.

    사전의 진짜 의미는 "매칭이 없으면 **할 말이 없다**"이다. 그건 '무반응'으로
    보내는 게 맞다. 점수가 있는 것들 사이에서만 상/하를 가른다.
    """
    s = np.array([x[0] for x in scores(rows) if x[1] > 0], dtype=float)
    if len(s) < 10:
        return -0.5, 0.5
    return np.quantile(s, [1 / 3, 2 / 3])


def predict(rows, lo, hi):
    """매칭 0개 → '무반응'(1). 사전이 침묵한 것을 침묵으로 옮긴다."""
    out = []
    for sc, hits in scores(rows):
        if hits == 0:
            out.append(1)
        else:
            out.append(0 if sc <= lo else (2 if sc >= hi else 1))
    return np.array(out)


def report(name, y, p):
    y, p = np.asarray(y), np.asarray(p)
    acc = float((y == p).mean())
    # 🔴 방향 정확도만 따로 본다. '무반응'을 맞히는 건 돈이 안 된다 —
    # 실제로 쓸 때 중요한 건 **오르는 걸 오른다고, 내리는 걸 내린다고** 하는 것이다.
    m = (y != 1) & (p != 1)
    dir_acc = float((y[m] == p[m]).mean()) if m.sum() else float("nan")
    # 🔴 치명적 오답 — 상승을 하락이라 하거나 그 반대. 이게 제일 비싸다.
    flip = float(((y == 0) & (p == 2)).sum() + ((y == 2) & (p == 0)).sum()) / len(y)
    print(f"\n[{name}]  표본 {len(y)}건")
    print(f"  전체 정확도   {acc:6.1%}   (3분류 기준선 33.3%)")
    print(f"  방향 정확도   {dir_acc:6.1%}   (무반응 제외 {int(m.sum())}건 · 기준선 50%)")
    print(f"  반대로 찍음   {flip:6.1%}   ← 낮을수록 좋다")
    print("       예측→   " + "".join(f"{l:>8}" for l in LABELS))
    for k, l in enumerate(LABELS):
        row = "".join(f"{int(((y == k) & (p == j)).sum()):>8}" for j in range(3))
        print(f"  실제 {l:<6}" + row)
    return dict(acc=acc, dir_acc=dir_acc, flip=flip)


def main():
    rows = load()
    tr, va, te = split(rows)
    tr, (va, te), bounds = make_labels(tr, [va, te])
    print(f"[데이터] 라벨 경계(훈련셋 3분위): {bounds[0]:+.2f}% / {bounds[1]:+.2f}%")
    from data import describe
    for n, r in (("훈련", tr), ("검증", va), ("테스트", te)):
        describe(n, r)

    lo, hi = fit_thresholds(tr)
    print(f"\n[사전] 점수 경계(훈련셋 3분위): {lo:+.1f} / {hi:+.1f}")

    # 사전이 아무 단어도 못 찾는 비율 — 이게 높으면 사전의 한계가 거기서 드러난다
    miss = sum(1 for _, hits in scores(te) if hits == 0) / len(te)
    print(f"[사전] 테스트셋에서 **매칭 단어가 하나도 없는** 헤드라인 {miss:.1%}")
    print("       (이 구간은 사전이 전부 '무반응'으로 찍는다 — 트랜스포머가 이길 여지)")

    report("사전 베이스라인 · 테스트셋", [r["y"] for r in te], predict(te, lo, hi))
    # 🔴 훈련셋은 3분위라 50/50/50 으로 균형이고, 그래서 '최빈 클래스'는 사실상
    # 동점이다. 대신 **테스트셋 클래스 분포**를 그대로 적어 둔다 — 시간 분할이라
    # 훈련셋 경계를 테스트 날에 적용하면 그날 시장 방향대로 분포가 기운다.
    import collections
    ct = collections.Counter(r["y"] for r in te)
    print(f"\n[참고] 테스트셋 클래스 분포: "
          + " · ".join(f"{LABELS[k]} {ct[k]} ({ct[k]/len(te):.1%})" for k in (0, 1, 2)))
    print("       한 클래스만 계속 찍었을 때의 정확도가 저 비율이다.")
    print("       10/19 는 상승이 많은 날이었다 — 시간 분할이라 이런 쏠림이 정상이다.")


if __name__ == "__main__":
    main()
