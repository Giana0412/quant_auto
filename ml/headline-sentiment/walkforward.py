#!/usr/bin/env python3
"""워크포워드(rolling-origin) 평가 — 날짜가 귀할 때 쓰는 방법.

── 🔴 왜 한 번 자르는 걸로는 안 되는가 ──────────────────────────────────
train.py 의 70/15/15 분할은 날짜가 27일일 때 **테스트 날짜 5일**을 준다.
그런데 같은 날 기사들은 같은 장을 공유한다 — 그날 지수가 오르면 그날
헤드라인은 대부분 '상승' 라벨을 받는다. 그래서 **독립 표본은 건수가 아니라
날짜 수**다. 테스트 5일이면 사실상 표본 5개이고, 그 5일이 어떤 장이었냐에
따라 점수가 통째로 흔들린다.

실제로 10/23 학습이 그랬다. 검증 날짜 1일(6건)로 best 체크포인트를 골랐고,
그 "검증정확도 83%" 는 6개 중 5개였다.

── 워크포워드가 하는 일 ─────────────────────────────────────────────────
    훈련 [1..k]            검증 [k+1,k+2]   테스트 [k+3]
    훈련 [1..k+1]          검증 [k+2,k+3]   테스트 [k+4]
    훈련 [1..k+2]          검증 [k+3,k+4]   테스트 [k+5]   ...

한 칸씩 밀면서 매번 다시 학습한다. 같은 27일에서 테스트 날짜가 5일이 아니라
**10~15일**이 나온다. 그리고 이 구조는 운용 상황과 정확히 같다 — 우리는 늘
오늘까지로 배워서 내일을 맞혀야 한다.

── 🔴 폴드마다 다시 해야 하는 것들 ──────────────────────────────────────
· 3분위 경계: **그 폴드의 훈련셋만으로** 다시 구한다. 전체로 구하면 미래를 본다
· 어휘사전 임계값도 마찬가지로 폴드마다 훈련셋에서 다시 맞춘다
· 모델도 폴드마다 처음부터 다시 학습한다(이어 학습하면 앞 폴드의 테스트를
  이미 본 상태가 된다)

── 비교 대상 ────────────────────────────────────────────────────────────
· **다수클래스**: 그 폴드 훈련셋에서 가장 흔했던 클래스를 테스트에 그대로 찍는다.
  🔴 테스트셋의 다수 클래스가 아니다 — 그건 실시간으로는 알 수 없는 값이라
  기준선으로 쓰면 모델에게 불리하게 과장된다. 둘 다 찍어서 구분해 둔다
· **어휘사전**: 운영 중인 score_text (§bridge.py). 이걸 못 넘으면 딥러닝을
  쓸 이유가 없다

실행:
  python walkforward.py                      # 기본(warmup 10 · val 2 · step 1)
  python walkforward.py --step 2             # 폴드 수를 반으로(빠르게)
  python walkforward.py --warmup 6 --val 1   # 날짜가 적을 때
  python walkforward.py --no-lexicon         # 어휘사전 비교 생략
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from transformers import AutoTokenizer
from transformers.utils import logging as hf_logging

# 폴드마다 인코더를 새로 불러오므로 같은 LOAD REPORT 와 진행바가 N번 찍혀
# 정작 봐야 할 폴드별 성적을 덮는다. train.py 는 한 번만 찍으니 그대로 둔다.
hf_logging.set_verbosity_error()
hf_logging.disable_progress_bar()

import baseline
from baseline import report
from data import LABELS, label_end, load
from model import ENCODER
from train import (add_common_args, class_loss, evaluate, fit, loader,
                   pick_device)

HERE = Path(__file__).resolve().parent
OUT = HERE / "runs" / "walkforward.json"


def tercile_labels(fit_rows, *others):
    """🔴 경계는 fit_rows(그 폴드의 학습 데이터)에서만 구한다."""
    ex = np.array([r["excess"] for r in fit_rows])
    lo, hi = np.quantile(ex, [1 / 3, 2 / 3])
    for rs in (fit_rows, *others):
        for r in rs:
            e = r["excess"]
            r["y"] = 0 if e <= lo else (2 if e >= hi else 1)
    return float(lo), float(hi)


def by_date(rows):
    d = {}
    for r in rows:
        d.setdefault(r["date"], []).append(r)
    return d


def purged(dates, buckets, i, val):
    """🔴 테스트 날짜 dates[i] 이전 중 **라벨이 테스트 진입 전에 확정된 날짜만** 쓴다.

    purge 없이 dates[:i] 를 다 쓰면 h=3 에서 훈련·검증 라벨이 테스트 기간 주가를
    이미 담는다. 같은 종목이 매일 다시 나오므로 그 종목 단어가 테스트 정답을 베낀다.
    2026-11-06 experiments.py 에서 purge 전후 IC 가 +0.17 → -0.12 로 뒤집혔다.
    검증 날짜도 같은 규칙으로 고른다(조기 종료가 누수된 검증셋을 보면 같은 문제다)."""
    ok = [d for d in dates[:i] if max(label_end(r) for r in buckets[d]) <= dates[i]]
    return ok[:-val], ok[-val:]


def folds(dates, warmup, val, step):
    """(훈련날짜, 검증날짜, 테스트날짜) 를 차례로 내놓는다. 확장창이다."""
    i = warmup + val
    while i < len(dates):
        te = dates[i:i + step]
        if not te:
            break
        yield dates[:i - val], dates[i - val:i], te
        i += step


def lexicon_fold(fit_rows, test_rows):
    """어휘사전 기준선 — 임계값을 폴드 훈련셋에서 맞춰 테스트에 적용."""
    lo, hi = baseline.fit_thresholds(fit_rows)
    return np.asarray(baseline.predict(test_rows, lo, hi))


def main():
    p = add_common_args(argparse.ArgumentParser())
    p.add_argument("--warmup", type=int, default=10,
                   help="첫 폴드가 쓰는 최소 학습 날짜 수")
    p.add_argument("--val", type=int, default=2,
                   help="조기 종료용 검증 날짜 수(학습창의 뒤쪽에서 뗀다)")
    p.add_argument("--step", type=int, default=1,
                   help="폴드당 테스트 날짜 수. 크게 하면 폴드가 줄어 빨라진다")
    p.add_argument("--no-lexicon", action="store_true",
                   help="어휘사전 비교를 생략한다")
    a = p.parse_args()

    device = pick_device()
    print(f"[환경] device={device} · encoder={ENCODER} · seed={a.seed}")

    rows = load()
    buckets = by_date(rows)
    dates = sorted(buckets)
    plan = list(folds(dates, a.warmup, a.val, a.step))
    if not plan:
        raise SystemExit(
            f"\n🔴 날짜가 {len(dates)}일뿐이라 폴드를 하나도 못 만든다.\n"
            f"   warmup {a.warmup} + val {a.val} + 테스트 1일 = "
            f"최소 {a.warmup + a.val + 1}일이 필요하다.\n"
            f"   더 모으거나 `--warmup {max(2, len(dates)-3)} --val 1` 로 줄여 볼 것.\n")

    print(f"[계획] 날짜 {len(dates)}일 ({dates[0]} ~ {dates[-1]}) → 폴드 {len(plan)}개")
    print(f"       warmup {a.warmup}일 · 검증 {a.val}일 · 폴드당 테스트 {a.step}일")
    print(f"       폴드마다 처음부터 다시 학습한다 — "
          f"최대 {a.epochs}에폭 × {len(plan)}폴드\n")

    tok = AutoTokenizer.from_pretrained(ENCODER)
    rec, all_y, all_p, all_lex, all_maj = [], [], [], [], []
    t_start = time.time()

    for k, (_, _, d_te) in enumerate(plan, 1):
        d_fit, d_val = purged(dates, buckets, dates.index(d_te[0]), a.val)
        # 🔴 폴드마다 시드를 다시 심는다. 안 그러면 뒤쪽 폴드일수록 난수
        #    상태가 달라져 "데이터가 늘어서 좋아진 것"과 구분이 안 된다.
        torch.manual_seed(a.seed)
        np.random.seed(a.seed)

        f_rows = [r for d in d_fit for r in buckets[d]]
        v_rows = [r for d in d_val for r in buckets[d]]
        t_rows = [r for d in d_te for r in buckets[d]]
        lo, hi = tercile_labels(f_rows, v_rows, t_rows)

        t0 = time.time()
        model, hist, best_ep = fit(f_rows, v_rows, tok, device, a, verbose=False)
        _, ty, tp = evaluate(model, loader(t_rows, tok, a.max_len, a.batch * 2),
                             device, class_loss(f_rows, device, verbose=False))

        # 🔴 실시간에 알 수 있는 기준선 — 훈련셋의 다수 클래스를 그대로 찍는다
        maj_k = int(np.bincount([r["y"] for r in f_rows], minlength=3).argmax())
        maj_p = np.full_like(ty, maj_k)
        acc = float((ty == tp).mean())
        maj_acc = float((ty == maj_p).mean())

        lex_acc = float("nan")
        if not a.no_lexicon:
            lp = lexicon_fold(f_rows, t_rows)
            lex_acc = float((ty == lp).mean())
            all_lex.append(lp)

        all_y.append(ty); all_p.append(tp); all_maj.append(maj_p)
        rec.append(dict(fold=k, test_dates=d_te, n_fit=len(f_rows),
                        n_test=len(t_rows), bounds=[lo, hi], best_ep=best_ep,
                        acc=acc, majority_acc=maj_acc, lexicon_acc=lex_acc,
                        majority_label=LABELS[maj_k], epochs_run=len(hist)))

        flag = "✅" if acc > maj_acc else "❌"
        lex_s = "   —  " if a.no_lexicon else f"{lex_acc:6.1%}"
        print(f"  폴드 {k:>2}/{len(plan)}  테스트 {d_te[0]}"
              f"{'~' + d_te[-1] if len(d_te) > 1 else '         '}"
              f"  학습 {len(f_rows):>5}건 → 테스트 {len(t_rows):>4}건"
              f"   모델 {acc:6.1%} {flag}  다수 {maj_acc:6.1%}  사전 {lex_s}"
              f"  ({time.time()-t0:.0f}초)")

        del model
        if device.type == "mps":
            torch.mps.empty_cache()

    y = np.concatenate(all_y); pr = np.concatenate(all_p)
    maj = np.concatenate(all_maj)
    print(f"\n{'='*78}\n전체 {len(plan)}폴드 · 테스트 날짜 "
          f"{sum(len(r['test_dates']) for r in rec)}일 · 예측 {len(y)}건"
          f"  ({time.time()-t_start:.0f}초)\n{'='*78}")

    # 🔴 폴드마다 3분위 경계가 다르므로 라벨 정의도 폴드마다 다르다.
    #    그래도 뜻은 일관된다 — "그 시점까지 알려진 분포에서의 상·중·하".
    #    이게 실제 운용 상황이다. 묶어서 보는 게 맞다.
    res = report("DistilBERT · 워크포워드 전체", y, pr)
    maj_all = float((y == maj).mean())
    wins = sum(1 for r in rec if r["acc"] > r["majority_acc"])

    print(f"\n[비교]  모델 {res['acc']:.1%}"
          f"  ·  다수클래스 {maj_all:.1%}"
          + ("" if a.no_lexicon else
             f"  ·  어휘사전 {float((y == np.concatenate(all_lex)).mean()):.1%}"))
    print(f"  폴드별 승패: 다수클래스 대비 {wins}승 {len(rec)-wins}패"
          f" ({wins/len(rec):.0%})")
    accs = np.array([r["acc"] for r in rec])
    print(f"  폴드 정확도 평균 {accs.mean():.1%} · 중앙값 {np.median(accs):.1%}"
          f" · 최저 {accs.min():.1%} · 최고 {accs.max():.1%}")
    print(f"  🔴 산포가 크면 폴드 수가 모자란 것이다. "
          f"한 폴드의 숫자로 결론 내지 말 것.")

    if res["acc"] <= maj_all:
        print("\n  🔴 다수클래스를 못 넘었다 — 모델이 배운 게 없다는 뜻이다.")
    elif wins <= len(rec) / 2:
        print("\n  ⚠️  전체 평균은 앞섰지만 폴드 승률이 절반 이하다. "
              "몇 폴드가 평균을 끌어올린 것일 수 있다.")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(dict(args=vars(a), dates=dates, folds=rec,
                                   pooled=res, majority_pooled=maj_all,
                                   fold_wins=wins),
                              ensure_ascii=False, indent=2))
    print(f"\n  기록 → {OUT}")


if __name__ == "__main__":
    main()
