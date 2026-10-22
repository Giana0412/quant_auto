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


def load(path=DATA, min_rows=50):
    rows = []
    for line in Path(path).read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("excess") is not None and r.get("title"):
            rows.append(r)
    rows.sort(key=lambda r: (r["date"], r["ticker"]))
    if len(rows) < min_rows:
        raise SystemExit(
            f"라벨된 데이터가 {len(rows)}건뿐이다. `python collect.py` 를 며칠 돌려 쌓아야 한다.\n"
            f"(yfinance 는 최근 1주일 기사만 준다 — 소급 수집이 안 된다)")
    return rows


def split(rows, val_frac=0.15, test_frac=0.15):
    """시간순 분할. **날짜 경계에서 자른다** — 같은 날이 두 쪽에 걸치면
    위에 적은 누수가 그대로 일어난다."""
    dates = sorted({r["date"] for r in rows})
    n = len(dates)
    i_val = int(n * (1 - val_frac - test_frac))
    i_test = int(n * (1 - test_frac))
    d_train, d_val = set(dates[:i_val]), set(dates[i_val:i_test])
    tr = [r for r in rows if r["date"] in d_train]
    va = [r for r in rows if r["date"] in d_val]
    te = [r for r in rows if r["date"] not in d_train and r["date"] not in d_val]
    if not (tr and va and te):
        raise SystemExit(f"날짜가 {n}일뿐이라 3분할이 안 된다. 더 모아야 한다.")
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
