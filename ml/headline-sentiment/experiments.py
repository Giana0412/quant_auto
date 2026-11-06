#!/usr/bin/env python3
"""라벨·필터 설정을 빠르게 훑는다 — DistilBERT 를 돌리기 **전에** 문제부터 고친다.

── 왜 ──────────────────────────────────────────────────────────────────────
2026-11-06 워크포워드(18일·6폴드): DistilBERT 32.3% · 다수클래스 39.6% · 어휘사전 29.1%.
모델도 사전도 무작위 이하다. 모델보다 **라벨이 잡음**일 가능성이 크다:
  1. 기사 주인공이 그 종목이 아니다. HUT 에 붙은 "CoreWeave Reverses Up…" 이
     HUT 수익률을 정답으로 받는다. 같은 제목이 2.6종목에 붙어 서로 다른 정답을 받는다.
  2. 진입 시점. 발행 UTC 날짜 종가로 들어가 16:00~20:00 ET 기사는 미래를 본다.
  3. 벤치가 ACWI 다 — 미국 종목에 글로벌 지수를 빼면 미국/해외 갭이 라벨에 남는다.
  4. 3분위를 전체 기간으로 자르면 "그날 장" 이 라벨을 정한다(같은 날 기사가 한쪽으로 쏠림).

DistilBERT 한 번이 26분이라 이걸로 조합을 훑을 수 없다. TF-IDF + 로지스틱(폴드당
1초)으로 **어느 라벨/필터에서 신호가 생기는지**만 먼저 본다. 고른 설정은
`--export` 로 헤드라인 파일을 만들어 walkforward.py 에 HEADLINES_DATA 로 넘긴다.

── 🔴 지키는 것 ─────────────────────────────────────────────────────────────
· 폴드는 walkforward.py 와 같은 확장창 — 테스트 날짜 이전으로만 학습
· 전체기간 3분위 경계는 폴드 훈련셋에서만 구한다
· 날짜 내 3분위(xs)는 **그 날짜 안의 상대 순위**가 정답이다. 테스트 날짜의
  실현 수익으로 정답을 정의하는 것이지 입력에 쓰는 게 아니라 누수가 아니다
· 설정을 많이 훑을수록 우연히 좋은 게 나온다. 테스트 날짜가 8~9일뿐이라
  **IC t값 2 미만은 잡음으로 읽는다.** 숫자 하나로 고르지 말 것.

실행:
  python experiments.py                 # 설정 표
  python experiments.py --refresh       # 가격·유니버스 다시 받기
  python experiments.py --export NAME   # 그 설정으로 라벨을 다시 매긴 jsonl 을 runs/ 에 쓴다
"""
import argparse
import collections
import json
import re
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from data import DATA

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
PX = RUNS / "px.pkl"
UNI = RUNS / "universe.json"
ET = ZoneInfo("America/New_York")
WARMUP = 6     # 거래일 기준. 13~15 세션에서 10이면 폴드가 3~5개뿐이다
MIN_PER_DATE = 20

# 회사명에서 주인공 판정에 쓰면 안 되는 흔한 단어
GENERIC = {"the", "inc", "corp", "corporation", "company", "group", "holdings", "holding",
           "international", "technologies", "technology", "global", "systems", "plc",
           "ltd", "limited", "co", "and", "of", "class", "trust", "energy", "financial",
           "american", "united", "first", "general", "national", "new", "services"}


# ── 데이터 ────────────────────────────────────────────────────────────────
def rows_all():
    out = []
    for line in Path(DATA).read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("title"):
            out.append(r)
    return out


def prices(tickers, refresh):
    if PX.exists() and not refresh:
        px = pd.read_pickle(PX)
        if set(tickers) <= set(px.columns):
            return px
    import yfinance as yf
    px = yf.download(sorted(set(tickers)), start="2026-10-01", interval="1d",
                     progress=False, auto_adjust=True)["Close"]
    RUNS.mkdir(exist_ok=True)
    px.to_pickle(PX)
    return px


def universe(refresh, tickers=()):
    """{티커: 회사명}. 🔴 screen_universe 에는 이름이 없다(sector·tags 뿐) —
    처음엔 거기서 name 을 읽어 전부 빈 문자열이었고, 그래서 '주인공' 필터가
    티커 매칭만으로 돌았고 가림은 모든 단어를 지웠다. yfinance shortName 을 받는다."""
    have = json.loads(UNI.read_text()) if UNI.exists() and not refresh else {}
    todo = [t for t in tickers if not have.get(t)]
    if todo:
        import yfinance as yf
        from concurrent.futures import ThreadPoolExecutor

        def one(t):
            try:
                i = yf.Ticker(t).info
                return t, i.get("shortName") or i.get("longName") or ""
            except Exception:
                return t, ""
        with ThreadPoolExecutor(8) as ex:
            have.update(dict(ex.map(one, todo)))
        RUNS.mkdir(exist_ok=True)
        UNI.write_text(json.dumps(have, ensure_ascii=False))
    return have


def name_tokens(name):
    toks = re.findall(r"[A-Za-z][A-Za-z&'.-]+", name or "")
    return [t.strip(".").lower() for t in toks if len(t) >= 4 and t.lower() not in GENERIC][:1]


def mentions(r, names):
    """제목이 그 종목을 직접 말하는가 — 티커(대문자 단어) 또는 회사명 첫 핵심 단어."""
    t = r["title"]
    if re.search(rf"(?<![A-Za-z]){re.escape(r['ticker'])}(?![A-Za-z])", t):
        return True
    low = t.lower()
    return any(re.search(rf"\b{re.escape(k)}", low) for k in name_tokens(names.get(r["ticker"], "")))


_MASK = {}


def mask(title, ticker, names):
    """종목 정체를 가린다 — **유니버스 전 종목**의 티커·회사명을 모두.

    🔴 안 가리면 TF-IDF 가 **회사 이름**을 외운다. purge 후 h=3 에서 배운 상승/하락
    단어 상위가 lockheed·micron·meta·palantir 같은 이름이었고 IC 가 7폴드 전부 음수였다
    (훈련기간 강세 종목이 그 뒤 되밀림). 그건 헤드라인 해석이 아니라 가격 반전이다.
    🔴 자기 종목만 가리면 안 된다 — 같은 제목이 평균 2.6종목에 붙고, 제목 속 회사는
    붙은 종목이 아닌 경우가 많다(HUT 행의 'CoreWeave'). 첫 시도가 그래서 실패했다.
    """
    if "re" not in _MASK:
        toks = set()
        for n in filter(None, names.values()):
            words = [w.strip(".").lower() for w in re.findall(r"[A-Za-z][A-Za-z&'.-]+", n or "")]
            toks |= {w for w in words[:2] if len(w) >= 4 and w not in GENERIC}
        syms = sorted({t for t in names} | {ticker}, key=len, reverse=True)
        toks.discard("")
        _MASK["re"] = re.compile(r"(?i)\b(" + "|".join(map(re.escape, sorted(toks, key=len, reverse=True))) + r")\w*")
        _MASK["sym"] = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(x) for x in syms if len(x) >= 2) + r")(?![A-Za-z])")
    t = _MASK["sym"].sub(" coname ", title)
    t = re.sub(rf"(?<![A-Za-z]){re.escape(ticker)}(?![A-Za-z])", " coname ", t)
    return _MASK["re"].sub(" coname ", t)


def entry_day(r, sessions):
    """진입 세션 날짜.
    strict: 발행시각 **이후** 첫 종가(16:00 ET). 발행시각이 없는 옛 행은 UTC 날짜 규칙.
    legacy: 수집기와 같은 규칙(발행 UTC 날짜 이후 첫 세션 종가)."""
    pub = r.get("published")
    if pub:
        p = datetime.fromisoformat(pub).astimezone(ET)
        d = p.date()
        first = d if p.time() < dtime(16, 0) else None
        for s in sessions:
            if (first is not None and s >= first) or s > d:
                return s
        return None
    d0 = datetime.fromisoformat(r["date"]).date()
    return next((s for s in sessions if s >= d0), None)


def legacy_day(r, sessions):
    d0 = datetime.fromisoformat(r["date"]).date()
    return next((s for s in sessions if s >= d0), None)


def build(rows, px, names, cfg):
    """cfg 에 따라 (title, date, excess) 행을 만든다. date = 진입 세션(분할 단위)."""
    bench = px[cfg["bench"]].dropna()
    sessions = list(bench.index.date)
    pos = {s: i for i, s in enumerate(sessions)}
    title_cnt = collections.Counter(r["title"] for r in rows)
    out = []
    for r in rows:
        if cfg["filter"] in ("mention", "mention_rel1") and not mentions(r, names):
            continue
        if cfg["filter"] in ("rel1", "mention_rel1"):
            rel = [x for x in (r.get("rel") or []) if x not in ("SPY", "QQQ", "DIA", "^GSPC")]
            if r.get("rel") is None or len(rel) > 1:
                continue
        if cfg["filter"] == "unique_title" and title_cnt[r["title"]] > 1:
            continue
        if cfg.get("needs_pub") and not r.get("published"):
            continue
        t = r["ticker"]
        if t not in px.columns:
            continue
        d = entry_day(r, sessions) if cfg["entry"] == "strict" else legacy_day(r, sessions)
        if d is None:
            continue
        i0, h = pos[d], cfg["h"]
        if i0 + h >= len(sessions):
            continue                    # 아직 h 일이 안 지났다
        s0, s1 = sessions[i0], sessions[i0 + h]
        try:
            a0, a1 = px.at[pd.Timestamp(s0), t], px.at[pd.Timestamp(s1), t]
        except KeyError:
            continue
        if not (np.isfinite(a0) and np.isfinite(a1)):
            continue
        b0, b1 = bench.loc[pd.Timestamp(s0)], bench.loc[pd.Timestamp(s1)]
        ex = (a1 / a0 - (b1 / b0)) * 100
        # 진입 전 h 세션의 초과수익 — 가격 반전/모멘텀 기준선용(입력으로 쓰는 게 아니다)
        past = np.nan
        if i0 - h >= 0:
            try:
                p0 = px.at[pd.Timestamp(sessions[i0 - h]), t]
                past = (a0 / p0 - bench.loc[pd.Timestamp(s0)] / bench.loc[pd.Timestamp(sessions[i0 - h])]) * 100
            except KeyError:
                pass
        title = mask(r["title"], r["ticker"], names) if cfg.get("mask") else r["title"]
        out.append(dict(title=title, past=float(past), date=s0.isoformat(), end=s1.isoformat(), ticker=t, excess=float(ex)))
    cnt = collections.Counter(r["date"] for r in out)
    return [r for r in out if cnt[r["date"]] >= MIN_PER_DATE]


def label(rows, mode, fit_rows=None):
    if mode == "xs":                     # 날짜 안에서의 상대 순위
        byd = collections.defaultdict(list)
        for r in rows:
            byd[r["date"]].append(r)
        for rs in byd.values():
            lo, hi = np.quantile([r["excess"] for r in rs], [1 / 3, 2 / 3])
            for r in rs:
                r["y"] = 0 if r["excess"] <= lo else (2 if r["excess"] >= hi else 1)
        return
    lo, hi = np.quantile([r["excess"] for r in fit_rows], [1 / 3, 2 / 3])
    for r in rows:
        r["y"] = 0 if r["excess"] <= lo else (2 if r["excess"] >= hi else 1)


# ── 평가 ──────────────────────────────────────────────────────────────────
def walk(rows, mode, lex=None):
    dates = sorted({r["date"] for r in rows})
    res = []
    for i in range(WARMUP, len(dates)):
        # 🔴 purge: 라벨 끝(진입+h 세션 종가)이 테스트 진입 종가 **이후**인 행은 뺀다.
        #   안 빼면 h=3 에서 훈련 라벨이 테스트 기간의 주가를 이미 담는다 — 같은 종목이
        #   매일 다시 나오므로 "이 종목 단어 → 상승" 이 테스트 정답을 베낀다.
        #   첫 실행(purge 없음)에서 h=3 IC +0.17, h=1 IC -0.13 으로 갈린 게 그 흔적이다.
        tr = [dict(r) for r in rows if r["end"] <= dates[i]]
        te = [dict(r) for r in rows if r["date"] == dates[i]]
        if mode == "xs":
            label(tr, "xs"); label(te, "xs")
        else:
            label(tr, "global", tr); label(te, "global", tr)
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, lowercase=True)
        Xtr = vec.fit_transform([r["title"] for r in tr])
        Xte = vec.transform([r["title"] for r in te])
        ytr = np.array([r["y"] for r in tr])
        yte = np.array([r["y"] for r in te])
        clf = LogisticRegression(C=0.5, max_iter=2000, class_weight="balanced").fit(Xtr, ytr)
        P = clf.predict_proba(Xte)
        score = P[:, list(clf.classes_).index(2)] - P[:, list(clf.classes_).index(0)]
        pred = clf.classes_[P.argmax(1)]
        maj = collections.Counter(ytr).most_common(1)[0][0]
        ex = np.array([r["excess"] for r in te])
        ic = spearmanr(score, ex).statistic
        up, dn = ex[pred == 2], ex[pred == 0]
        row = dict(date=dates[i], n=len(te), acc=float((pred == yte).mean()),
                   maj=float((yte == maj).mean()), ic=float(ic),
                   ls=float(up.mean() - dn.mean()) if len(up) and len(dn) else np.nan)
        if lex is not None:
            ls_ = np.array([lex.get(r["title"], 0) for r in te], float)
            row["lex_ic"] = float(spearmanr(ls_, ex).statistic) if ls_.std() else 0.0
        pa = np.array([r["past"] for r in te])
        ok = np.isfinite(pa)
        row["rev_ic"] = float(spearmanr(-pa[ok], ex[ok]).statistic) if ok.sum() > 10 else np.nan
        res.append(row)
    return res


def summarize(name, res, n_rows):
    if not res:
        return dict(name=name, rows=n_rows, folds=0)
    ic = np.array([r["ic"] for r in res])
    out = dict(name=name, rows=n_rows, folds=len(res),
               acc=np.mean([r["acc"] for r in res]), maj=np.mean([r["maj"] for r in res]),
               wins=sum(r["acc"] > r["maj"] for r in res),
               ic=ic.mean(), ic_t=ic.mean() / (ic.std(ddof=1) / np.sqrt(len(ic))) if len(ic) > 1 else np.nan,
               ls=np.nanmean([r["ls"] for r in res]))
    rv = np.array([r["rev_ic"] for r in res], float)
    rv = rv[np.isfinite(rv)]
    out["rev_ic"] = rv.mean() if len(rv) else np.nan
    out["rev_t"] = rv.mean() / (rv.std(ddof=1) / np.sqrt(len(rv))) if len(rv) > 1 else np.nan
    if "lex_ic" in res[0]:
        li = np.array([r["lex_ic"] for r in res])
        out["lex_ic"] = li.mean()
        out["lex_t"] = li.mean() / (li.std(ddof=1) / np.sqrt(len(li))) if li.std() else 0.0
    return out


CONFIGS = {
    # 이름: 현재 수집기와 같은 라벨에서 출발해 한 축씩 바꾼다
    "base(현재)":            dict(entry="legacy", bench="ACWI", h=3, label="global", filter="all"),
    "진입=strict":            dict(entry="strict", bench="ACWI", h=3, label="global", filter="all"),
    "+벤치=SPY":              dict(entry="strict", bench="SPY", h=3, label="global", filter="all"),
    "+날짜내순위":            dict(entry="strict", bench="SPY", h=3, label="xs", filter="all"),
    "+주인공":                dict(entry="strict", bench="SPY", h=3, label="xs", filter="mention"),
    "+날짜내순위·가림":       dict(entry="strict", bench="SPY", h=3, label="xs", filter="all", mask=True),
    "+주인공·가림":           dict(entry="strict", bench="SPY", h=3, label="xs", filter="mention", mask=True),
    "전체 h=1 가림":          dict(entry="strict", bench="SPY", h=1, label="xs", filter="all", mask=True),
    "주인공 h=1 가림":        dict(entry="strict", bench="SPY", h=1, label="xs", filter="mention", mask=True),
    "+주인공·단독":           dict(entry="strict", bench="SPY", h=3, label="xs", filter="mention_rel1"),
    "주인공 h=1":             dict(entry="strict", bench="SPY", h=1, label="xs", filter="mention"),
    "주인공 h=2":             dict(entry="strict", bench="SPY", h=2, label="xs", filter="mention"),
    "주인공 h=1 global":      dict(entry="strict", bench="SPY", h=1, label="global", filter="mention"),
    "고유제목 h=1":           dict(entry="strict", bench="SPY", h=1, label="xs", filter="unique_title"),
    "전체 h=1":               dict(entry="strict", bench="SPY", h=1, label="xs", filter="all"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--export", metavar="NAME")
    ap.add_argument("--no-lexicon", action="store_true")
    a = ap.parse_args()

    raw = rows_all()
    tickers = sorted({r["ticker"] for r in raw}) + ["SPY", "ACWI"]
    px = prices(tickers, a.refresh)
    names = universe(a.refresh, tickers[:-2])
    last = px["SPY"].dropna().index[-1].date()
    print(f"[데이터] 헤드라인 {len(raw)}건 · 가격 마지막 종가 {last} · 회사명 {len(names)}개")

    if a.export:
        cfg = CONFIGS[a.export]
        rows = build(raw, px, names, cfg)
        out = RUNS / f"headlines-{re.sub(r'[^A-Za-z0-9=]+', '_', a.export).strip('_') or 'cfg'}.jsonl"
        if cfg["label"] == "xs":
            # walkforward.py 는 전체기간 3분위를 쓴다. 날짜 내 순위를 그대로 쓰게
            # excess 를 날짜 내 백분위(-50~+50)로 바꿔 넘긴다 — 3분위 경계가 곧 날짜 내 3분위가 된다.
            byd = collections.defaultdict(list)
            for r in rows:
                byd[r["date"]].append(r)
            for rs in byd.values():
                ranks = pd.Series([r["excess"] for r in rs]).rank(pct=True).values
                for r, q in zip(rs, ranks):
                    r["raw_excess"], r["excess"] = r["excess"], float(q * 100 - 50)
        with out.open("w") as f:
            for i, r in enumerate(rows):
                f.write(json.dumps(dict(r, id=str(i)), ensure_ascii=False) + "\n")
        print(f"[내보냄] {a.export}: {len(rows)}건 · {len({r['date'] for r in rows})}일 → {out}")
        return

    lex = None
    if not a.no_lexicon:
        import baseline
        titles = [{"title": t} for t in {r["title"] for r in raw}]
        lex = {r["title"]: s for r, (s, _) in zip(titles, baseline.scores(titles))}

    table = []
    for name, cfg in CONFIGS.items():
        rows = build(raw, px, names, cfg)
        res = walk(rows, cfg["label"], lex)
        s = summarize(name, res, len(rows))
        s["dates"] = len({r["date"] for r in rows})
        table.append(s)
        print(f"  {name:<20} {s['rows']:>5}건 {s['dates']:>2}일 폴드{s['folds']:>2}"
              + (f"  정확도 {s['acc']*100:5.1f}% (다수 {s['maj']*100:4.1f}%, {s['wins']}승)"
                 f"  IC {s['ic']:+.3f} (t={s['ic_t']:+.2f})  상승-하락 {s['ls']:+.2f}%p"
                 + f"  | 반전 IC {s['rev_ic']:+.3f} (t={s['rev_t']:+.2f})"
                 + (f"  | 사전 IC {s['lex_ic']:+.3f} (t={s['lex_t']:+.2f})" if "lex_ic" in s else "")
                 if s["folds"] else ""), flush=True)
    RUNS.mkdir(exist_ok=True)
    (RUNS / "experiments.json").write_text(json.dumps(
        dict(run=datetime.now().isoformat(timespec="minutes"), last_close=str(last), table=table),
        ensure_ascii=False, indent=1, default=float))
    print("\n  IC = 모델 점수(상승확률-하락확률)와 실제 초과수익의 날짜별 순위상관 평균.")
    print("  t = IC 평균 / 표준오차. 테스트 날짜가 적어 |t|<2 는 잡음으로 읽는다.")


if __name__ == "__main__":
    main()
