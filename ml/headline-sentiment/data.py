#!/usr/bin/env python3
"""데이터셋 · 분할 · 토크나이즈.

── 🔴 분할은 반드시 시간순이다 ───────────────────────────────────────────
랜덤 분할을 하면 **같은 날 같은 사건의 기사가 훈련셋과 테스트셋에 나뉘어 들어간다.**
"애플 실적 호조" 기사가 열 곳에서 나오는데 다섯 개로 배우고 다섯 개로 시험하면
정확도가 치솟는다. 그건 학습이 아니라 **정답지를 본 것**이다.

시계열 분할은 운용 상황과도 같다 — 우리는 늘 과거로 배우고 미래를 맞혀야 한다.

── 🔴 3분위 경계는 훈련셋에서만 구한다 ───────────────────────────────────
라벨을 상·중·하로 자를 때 전체 데이터의 분위수를 쓰면 **테스트셋의 분포를
미리 본 것**이다(누수). 훈련셋에서 구한 경계를 테스트셋에 그대로 적용한다.
그래서 테스트셋의 클래스 비율은 1/3씩이 아니고, 그게 정상이다.

── 왜 3분류인가 ──────────────────────────────────────────────────────────
2분류(올랐나/내렸나)는 ±0.01% 짜리 잡음까지 정답을 강요한다. 가운데 구간을
'무반응'으로 빼면 모델이 **실제로 움직인 뉴스**에 집중한다. 3분위로 자르면
클래스가 균형을 이뤄 정확도 기준선이 33.3% 로 깔끔해진다.
"""
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

HERE = Path(__file__).resolve().parent
# 🔴 데이터는 **한 곳에만** 쌓는다.
# 체인은 운영 클론(~/orca/projects/quant_auto)에서 돌고 학습은 개발 클론에서
# 하는데, 스크립트 옆(HERE/data)에 쌓으면 두 벌로 갈라져 서로 다른 걸 본다.
# 다른 누적 데이터(book-log·regime-log)가 이미 사는 곳에 같이 둔다.
# 환경변수로 덮어쓸 수 있게 열어 둔다(테스트·다른 머신용).
import os
DATA = Path(os.environ.get(
    "HEADLINES_DATA",
    "/Users/gyuhyeongkim/orca/projects/quant_auto"
    "/personal/10-market/_headlines/headlines.jsonl"))
LABELS = ["하락", "무반응", "상승"]       # 0, 1, 2

# 🔴 날짜가 모자라면 성적이 "나쁜" 게 아니라 **측정 자체가 불가능**하다.
# 분할은 날짜 경계에서 자르므로(위 참조) 고유 날짜가 6일이면 검증셋도
# 테스트셋도 하루짜리가 된다. 하루 = 사실상 표본 하나다. 그날 장이 올랐으면
# '상승'만 찍어도 40%가 나오고, 그걸 모델 성적으로 착각하게 된다.
# yfinance 는 최근 1주일 기사만 주므로 소급 수집이 안 된다 — 날짜는
# 체인이 하루에 하나씩만 늘려 준다. 기다리는 것 말고 방법이 없다.
MIN_DATES = 20

# 🔴 **얇은 날짜는 날짜로 세지 않는다.**
# MIN_DATES 는 "고유 날짜 20일"을 요구하는데, 세는 방식이 틀리면 가드가 통째로
# 무력해진다. 실측(2026-10-25):
#   10/22 목  896건        10/18 일  6건
#   10/23 금  698건        10/25 일  3건
# 둘 다 카운트에서는 똑같이 **1일**이다. 20일을 채워도 그중 다섯 날이 한 자릿수면
# 실질은 15일이고, 하필 그 하루가 테스트 폴드로 잡히면 평가가 또 복권이 된다.
# (6건짜리 검증셋으로 "검증정확도 83%" 를 뽑은 게 2026-10-23 의 실패였다.)
#
# 20건이면 정확도가 5% 단위로 끊긴다 — 거칠지만 읽을 수는 있다. 6건(16.7% 단위)은
# 읽을 수 없다. 그래서 하한을 20건에 둔다. 기준에 못 미치는 날짜는 **빼고 센다.**
# 빠지는 행이 아깝지 않다 — 3~6건은 학습에 기여하는 게 거의 없고, 평가만 망친다.
MIN_ROWS_PER_DATE = 20


def load(path=DATA, min_rows=50, min_rows_per_date=MIN_ROWS_PER_DATE):
    rows = []
    for line in Path(path).read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("excess") is not None and r.get("title"):
            rows.append(r)
    # 🔴 **분할 단위는 달력 날짜가 아니라 진입 거래일이다.** 라벨은 그 날짜 이후 첫
    # 세션 종가로 진입하므로 토·일 기사는 월요일 기사와 **같은 가격창**을 쓴다 —
    # 독립 표본이 아니다. 달력으로 세면 19일이 실제로는 13거래일이었다(2026-11-06).
    # 주말·월요일이 훈련/테스트로 갈리면 같은 정답을 양쪽에서 보는 누수이기도 하다.
    # 원래 날짜는 date_cal 에 남긴다. (미국 공휴일은 무시 — 드물고, 틀려도 하루 차이)
    for r in rows:
        r["date_cal"] = r["date"]
        r["date"] = str(np.busday_offset(np.datetime64(r["date"]), 0, roll="forward"))
    rows.sort(key=lambda r: (r["date"], r["ticker"]))

    # 얇은 날짜를 떨어낸다. **조용히 버리지 않는다** — 날짜가 몇 개 줄었는지
    # 보여주지 않으면 D-day 계산이 왜 밀렸는지 사람이 알 수 없다.
    if min_rows_per_date > 1:
        import collections
        cnt = collections.Counter(r["date"] for r in rows)
        thin = sorted(d for d, c in cnt.items() if c < min_rows_per_date)
        if thin:
            rows = [r for r in rows if cnt[r["date"]] >= min_rows_per_date]
            print(f"[날짜] 얇은 날짜 {len(thin)}일 제외 (각 {min_rows_per_date}건 미만): "
                  + ", ".join(f"{d}({cnt[d]}건)" for d in thin))

    if len(rows) < min_rows:
        raise SystemExit(
            f"라벨된 데이터가 {len(rows)}건뿐이다. `python collect.py` 를 며칠 돌려 쌓아야 한다.\n"
            f"(yfinance 는 최근 1주일 기사만 준다 — 소급 수집이 안 된다)")
    return rows


def label_end(r):
    """라벨이 확정되는 거래일(진입 + horizon). experiments.py --export 행은 `end` 를
    갖고, 수집기 원본 행은 없으니 영업일로 계산한다(공휴일 무시 — 하루 길게 잡혀
    purge 가 보수적인 쪽으로 틀린다)."""
    if r.get("end"):
        return r["end"]
    return str(np.busday_offset(np.datetime64(r["date"]), int(r.get("horizon") or 3),
                                roll="forward"))


def split(rows, val_frac=0.15, test_frac=0.15):
    """시간순 분할. **날짜 경계에서 자른다** — 같은 날이 두 쪽에 걸치면
    위에 적은 누수가 그대로 일어난다.

    🔴 그리고 **purge** 한다. h=3 이면 훈련 마지막 날짜들의 라벨이 검증·테스트 기간
    주가로 정해진다 — 같은 종목이 매일 다시 나오므로 그 종목 단어가 정답을 베낀다
    (2026-11-06 experiments.py: purge 전후 IC +0.17 → -0.12). 라벨 끝이 다음 구간
    시작보다 늦은 행은 뺀다."""
    dates = sorted({r["date"] for r in rows})
    n = len(dates)
    i_val = int(n * (1 - val_frac - test_frac))
    i_test = int(n * (1 - test_frac))
    d_train, d_val = set(dates[:i_val]), set(dates[i_val:i_test])
    tr = [r for r in rows if r["date"] in d_train]
    va = [r for r in rows if r["date"] in d_val]
    te = [r for r in rows if r["date"] not in d_train and r["date"] not in d_val]
    if va and te:
        v0, t0 = min(r["date"] for r in va), min(r["date"] for r in te)
        tr = [r for r in tr if label_end(r) <= v0]
        va = [r for r in va if label_end(r) <= t0]
    if not (tr and va and te):
        raise SystemExit(
            f"날짜가 {n}거래일뿐이라 purge 후 3분할이 안 된다(훈련 {len(tr)} · 검증 {len(va)} · "
            f"테스트 {len(te)}건).\n검증 구간이 horizon 보다 짧으면 purge 로 통째로 빠진다. "
            f"더 모으거나 walkforward.py 를 쓸 것.")
    return tr, va, te


def make_labels(train, others):
    """훈련셋 3분위로 경계를 정하고 나머지에 **같은 경계**를 적용한다."""
    ex = np.array([r["excess"] for r in train])
    lo, hi = np.quantile(ex, [1 / 3, 2 / 3])

    def tag(rs):
        for r in rs:
            e = r["excess"]
            r["y"] = 0 if e <= lo else (2 if e >= hi else 1)
        return rs

    return tag(train), [tag(o) for o in others], (float(lo), float(hi))


def check_dates(rows, min_dates=MIN_DATES, force=False):
    """학습을 시작하기 전에 날짜가 충분한지 본다. 모자라면 **멈춘다**.

    의미 없는 best.pt 를 만들어 두면 나중에 history.json 의 검증정확도만 보고
    "83% 나왔네" 로 읽게 된다. 실제로 그 83% 는 검증셋 6건 중 5건이었다.
    """
    dates = sorted({r["date"] for r in rows})      # load() 가 이미 거래일로 바꿔 둔다
    n = len(dates)
    i_val, i_test = int(n * 0.70), int(n * 0.85)
    n_tr, n_va, n_te = i_val, i_test - i_val, n - i_test
    line = (f"[날짜] 진입 거래일 {n}일 ({dates[0]} ~ {dates[-1]})"
            f" → 훈련 {n_tr}일 · 검증 {n_va}일 · 테스트 {n_te}일")
    if n >= min_dates:
        print(line)
        return
    msg = (
        f"\n{line}\n"
        f"\n🔴 날짜가 {n}일뿐이라 학습 결과를 **측정할 수 없다** (최소 {min_dates}일).\n"
        f"   테스트셋이 {n_te}일이면 그날 장이 어땠는지가 점수의 전부다.\n"
        f"   건수(={len(rows)}건)는 문제가 아니다 — 날짜가 문제다.\n"
        f"\n   체인이 하루에 한 날짜씩 쌓는다. yfinance 는 최근 1주일 기사만\n"
        f"   주므로 지난 날짜는 소급해서 못 채운다. 기다리는 수밖에 없다.\n"
        f"   남은 날짜: {min_dates - n}일.\n"
        f"   🔴 거래일로 센다 — 주말 기사는 월요일과 같은 가격창이라 하루로 안 친다.\n"
        f"   그래서 달력으로 {min_dates - n}일이 아니라 그 1.4배쯤 걸린다.\n"
        f"\n   진행 상황: python collect.py --stats\n"
        f"   그래도 돌려보려면: python train.py --force  (성적은 믿지 말 것)\n")
    if force:
        print(msg + "\n   --force 가 켜져 있어 그대로 진행한다. "
              "아래 성적은 **참고용도 아니다**.\n")
        return
    raise SystemExit(msg)


def majority_baseline(test_rows):
    """테스트셋에서 '가장 많은 클래스만 찍기'의 정확도.

    🔴 모델 정확도는 **반드시 이것과 비교**해야 한다. 3분류라고 기준선이
    33.3% 인 게 아니다 — 테스트셋은 훈련셋 경계를 쓰므로 분포가 기운다.
    """
    import collections
    c = collections.Counter(r["y"] for r in test_rows)
    k, n = c.most_common(1)[0]
    return LABELS[k], n / len(test_rows)


class Headlines(Dataset):
    """토크나이즈는 __init__ 에서 한 번에 한다 — 헤드라인은 짧고 건수도 적어
    메모리에 다 올라간다. __getitem__ 에서 매번 토크나이즈하면 DataLoader
    워커가 CPU 를 다 먹는다(8GB 머신에서 체감된다)."""

    def __init__(self, rows, tokenizer, max_len=64):
        self.rows = rows
        enc = tokenizer([r["title"] for r in rows], truncation=True,
                        max_length=max_len, padding="max_length",
                        return_tensors="pt")
        self.ids = enc["input_ids"]
        self.mask = enc["attention_mask"]
        self.y = torch.tensor([r["y"] for r in rows], dtype=torch.long)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.ids[i], self.mask[i], self.y[i]


def describe(name, rows):
    import collections
    c = collections.Counter(r["y"] for r in rows)
    span = f"{rows[0]['date']} ~ {rows[-1]['date']}"
    dist = " ".join(f"{LABELS[k]} {c[k]:>4}" for k in (0, 1, 2))
    print(f"  {name:<6} {len(rows):>5}건  {span}   {dist}")
