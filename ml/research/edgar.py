#!/usr/bin/env python3
"""SEC EDGAR 10-K·10-Q 본문 수집·정제·섹션 추출·전년 대비 유사도 (KAN-32 Lazy Prices 의 재료).

── 왜 ──────────────────────────────────────────────────────────────────────
KAN-23 의 교훈은 "모델보다 입력"이었다. 가격·거래량·실적 숫자만으로는 월 수익 OOS R² 가 0 을 못 넘었다.
Cohen–Malloy–Nguyen (2020, JF "Lazy Prices") 은 기업이 10-K/10-Q 문장을 전년과 다르게 고치면
(유사도 낮음 = '변경자') 이후 수익이 나쁘고, 시장이 이를 늦게 반영한다고 보고했다. 가격에 없는 새 정보원이다.
이 모듈은 그 재료(공시 목록, 정제 본문, 섹션 위치, 유사도 표)를 만들고 캐시한다. 연구는 lazy_prices.py.

── 경로 · 캐시 (QA_RESEARCH_RUNS/edgar/, gitignore) ─────────────────────────────
cik_map.json         티커 → CIK (+ 방법: tickers 파일 / 회사명 / 실패). 실패 목록이 생존 편향 진단이다.
submissions/         CIK 별 공시 목록 JSON (data.sec.gov, 10-K·10-Q 행만 남겨 압축 저장)
filings.parquet      한 행 = 공시 한 건: ticker·cik·form·filing_date·accept_utc·report_date·acc·primary
text/{cik}/{acc}.json.gz   정제 본문 하나 + 섹션 위치(문자 오프셋). 🔴 원본 HTML 은 저장하지 않는다(디스크 ~11GB).
errors.jsonl         받기·정제 실패 기록 (재실행 시 다시 시도하지 않으려면 --skip-errors)
sims.parquet         한 행 = 공시 한 건: 비교 대상(전년 같은 종류) 과의 유사도·길이 변화·이용 가능 세션

── 정의 ────────────────────────────────────────────────────────────────────
대상 공시   form ∈ {10-K, 10-Q}, filing_date 2012-01-01 이후. 🔴 /A(정정)는 뺀다 — 정정은 대개 일부 항목
           (Part III, 서명, 오탈자)만 다시 내는 문서라 원본과 비교하면 유사도가 기계적으로 낮게 나온다.
           논문도 원본 공시끼리 비교한다. 10-KT(결산기 변경)·10-K405(2003년 폐지)도 뺀다.
정제        ix:header·script·style·주석 제거 → 블록 태그 끝은 줄바꿈, 셀 끝은 공백, 나머지 태그 삭제 →
           HTML 엔티티 복원 → 공백 정리 → 글자가 하나도 없는 줄(숫자만 있는 표 칸·쪽 번호) 삭제.
섹션        정제 본문에서 줄 머리의 제목 정규식으로 시작점, 다음 항목 제목으로 끝점을 찾는다. 시작 후보가
           여럿이면(목차·본문) 가장 긴 구간을 고른다 — 목차 항목은 몇십 글자라서 진짜 본문이 이긴다.
           10-K  rf  = Item 1A Risk Factors → Item 1B/1C/2      mda = Item 7 MD&A → Item 7A/8
           10-Q  mda = (Part I) Item 2 MD&A → Item 3/4          rf  = (Part II) Item 1A → Item 2–6
           최소 길이(10-K 1,000자 · 10-Q rf 80자 · 10-Q mda 1,000자)보다 짧으면 실패로 본다(본문이 Exhibit 13
           으로 '참조 편입'된 10-K 의 MD&A 등).
토큰        소문자 알파벳 연속([a-z]+), 2글자 이상. 어간 추출·불용어 제거 없음(논문의 단순 bag-of-words).
유사도      cos = 단어 빈도 벡터의 코사인, jac = 단어 집합의 자카드 |A∩B|/|A∪B| (CMN 2020 식).
           비교 대상: 10-K → 직전 10-K (보고기간 끝이 300~430일 전), 10-Q → 전년 같은 분기 10-Q
           (보고기간 끝이 330~400일 전). 보고기간이 없으면 filing_date 로 같은 창을 쓴다.
dlen        log(토큰 수 / 비교 대상 토큰 수) — 문서가 길어졌는가.

── 🔴 미래 정보가 새는 곳과 막은 방법 ────────────────────────────────────────
🔴 공개 시각: acceptanceDateTime(EDGAR 접수 시각, submissions JSON 에서 UTC — Apple 10-K 0000320193-23-000106
   의 헤더 ACCEPTANCE-DATETIME 20231102180827(ET) = JSON 2023-11-02T22:08:27Z 로 확인) → 뉴욕 시각으로 바꿔
   **그 시각보다 엄격히 뒤에 열리는 첫 세션**(09:30 ET 개장)을 이용 가능일 avail 로 둔다.
   09:30 전 접수 → 그날, 장중·장후(예: 16:30) 접수 → 다음 세션. 그래서 t 장후 공시는 t 행에 안 보인다.
   장중 접수를 t 종가에 쓰는 것도 가능하지만 보수적으로 다음 세션으로 민다.
   filing_date 는 쓰지 않는다 — 17:30 이후 접수분은 다음 영업일이 filing_date 라 하루 어긋나고,
   반대로 filing_date 만 보면 접수 시각(장 전·장중·장후)을 모른다.
🔴 월말 행 t 는 avail ≤ t 인 가장 최근 공시만 본다(as-of 병합, asof_features). 정보 나이 age = t − avail.
🔴 비교 대상은 그 공시보다 **먼저** 접수된 공시뿐이다(보고기간 창 + 접수 시각 순서 둘 다 확인).
🔴 유사도의 백분위·순위는 연구 쪽에서 날짜별 횡단면으로만 만든다(panel.rank_normalize). 여기서는 원값만.
🔴 티커 → CIK 는 **오늘의** SEC 티커 파일이다. 편출·피인수 종목은 거기 없거나, 같은 티커를 지금 다른 회사가
   쓴다. 그래서 편출 종목은 (a) 그 CIK 가 편입 기간에 10-K/10-Q 를 낸 적이 있어야 인정하고 (b) 없으면 위키백과
   S&P 500 변경 표의 회사명으로 SEC 회사명 목록에서 찾는다. 그래도 안 되면 결측 — 생존 편향 진단에 센다.
🔴 지주사 재편(예: Google→Alphabet) 으로 CIK 가 바뀐 경우 예전 CIK 공시는 안 잡힌다 → 그 기간은 결측.

── 예의 (SEC fair access) ────────────────────────────────────────────────
User-Agent 는 환경변수 QA_SEC_UA, 없으면 파일 ~/.config/quant_auto/sec_ua 첫 줄(경로는 QA_SEC_UA_FILE 로 바꿈).
둘 다 없으면 멈춘다. 🔴 UA 내용은 출력·로그·커밋에 남기지 않는다. 초당 8회 이하(프로세스 W 개가 각자 8/W),
429/503/5xx 는 지수 백오프로 재시도. 이미 받은 공시는 건너뛴다(재시작 가능).

실행 (ml/ 에서):
  ../headline-sentiment/.venv/bin/python -m research.edgar index       # CIK 매핑 + 공시 목록 (~2분)
  ../headline-sentiment/.venv/bin/python -m research.edgar fetch       # 본문 받기·정제 (재시작 가능, ~1–2시간)
  ../headline-sentiment/.venv/bin/python -m research.edgar sims        # 유사도 표
  ../headline-sentiment/.venv/bin/python -m research.edgar coverage    # 연도별 공시 수·매핑률·섹션 추출률
"""
from __future__ import annotations

import argparse
import gzip
import html as _html
import json
import math
import os
import re
import shutil
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from . import panel

EDGAR = panel.RUNS / "edgar"
START = "2012-01-01"
FORMS = ("10-K", "10-Q")
RATE = 8.0                       # 초당 요청 상한 (SEC 는 10)
MAX_BYTES = 60_000_000           # 이보다 큰 본문은 건너뛴다(대개 이미지 내장)
MIN_FREE_GB = 4.0                # 홈 디스크 여유가 이보다 작으면 받기를 멈춘다
WIKI_CHANGES = ("https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid=1340186477")


# ── User-Agent · 요청 ────────────────────────────────────────────────────────

def user_agent() -> str:
    """QA_SEC_UA → 없으면 QA_SEC_UA_FILE(기본 ~/.config/quant_auto/sec_ua) 첫 줄. 🔴 값은 출력하지 않는다."""
    ua = os.environ.get("QA_SEC_UA", "").strip()
    if ua:
        return ua
    f = Path(os.environ.get("QA_SEC_UA_FILE", Path.home() / ".config" / "quant_auto" / "sec_ua")).expanduser()
    if f.exists():
        first = f.read_text().splitlines()[:1]
        if first and first[0].strip():
            return first[0].strip()
    raise SystemExit("SEC User-Agent 가 없다: 환경변수 QA_SEC_UA 를 두거나, 파일 ~/.config/quant_auto/sec_ua "
                     "(또는 QA_SEC_UA_FILE 가 가리키는 파일) 첫 줄에 '이름 연락처' 를 적어라. SEC 는 연락처 없는 UA 를 403 으로 막는다.")


class Client:
    """한 프로세스용 HTTP 클라이언트 — 요청 간격 ≥ 1/rate 초, 429/503/5xx·연결 오류는 백오프 재시도."""

    def __init__(self, rate: float = RATE, tries: int = 6):
        import requests
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"})
        self.gap, self.tries, self.last = 1.0 / rate, tries, 0.0

    def get(self, url: str, stream: bool = False):
        import requests
        for k in range(self.tries):
            w = self.last + self.gap - time.monotonic()
            if w > 0:
                time.sleep(w)
            self.last = time.monotonic()
            try:
                r = self.s.get(url, timeout=60, stream=stream)
            except requests.RequestException:
                time.sleep(min(60, 2 ** k))
                continue
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503, 504):
                r.close()
                time.sleep(min(120, 2 ** (k + 1)))
                continue
            r.raise_for_status()
        raise RuntimeError(f"재시도 {self.tries}회 실패: {url}")

    def json(self, url: str):
        return self.get(url).json()

    def body(self, url: str, max_bytes: int = MAX_BYTES) -> bytes | None:
        """🔴 디스크에 쓰지 않고 메모리로만 받는다. max_bytes 초과면 None."""
        r = self.get(url, stream=True)
        buf, n = [], 0
        for ch in r.iter_content(1 << 16):
            buf.append(ch)
            n += len(ch)
            if n > max_bytes:
                r.close()
                return None
        return b"".join(buf)


def free_gb(path: Path = Path.home()) -> float:
    return shutil.disk_usage(path).free / 1e9


# ── 정제 · 섹션 (순수 함수 — 테스트 대상) ─────────────────────────────────────

_RE_DROP = re.compile(r"<!--.*?-->|<(ix:header|script|style|head|title)\b.*?</\1\s*>", re.S | re.I)
_RE_BLOCK = re.compile(r"<\s*(?:/\s*(?:p|div|tr|li|h[1-6]|table|center|ul|ol|blockquote|pre)|br|hr)\b[^>]*>", re.I)
_RE_CELL = re.compile(r"<\s*/\s*t[dh]\s*>", re.I)
_RE_TAG = re.compile(r"<[^>]*>")
_RE_SP = re.compile(r"[ \t\r\f\v  -​  　]+")
_RE_LETTER = re.compile(r"[A-Za-z]")


def clean_html(raw: str | bytes) -> str:
    """HTML(또는 텍스트) → 줄 단위 평문. 블록 끝은 줄바꿈이라 제목이 줄 머리에 온다(섹션 정규식이 기댄다)."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    s = _RE_DROP.sub(" ", raw)
    s = _RE_BLOCK.sub("\n", s)
    s = _RE_CELL.sub(" ", s)
    s = _RE_TAG.sub("", s)
    s = _html.unescape(s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    lines = (_RE_SP.sub(" ", ln).strip() for ln in s.split("\n"))
    return "\n".join(ln for ln in lines if _RE_LETTER.search(ln))


_H = r"^[^\S\n]*(?:part\s+i{1,2}\W{0,5})?item[^\S\n]*"          # 줄 머리 'Item' (앞에 'Part II,' 허용)
SECTIONS = {
    "10-K": {
        "rf": (_H + r"1a\b[\W_]*risk\s+factors", _H + r"(?:1b|1c|2|3)\b", 1000),
        "mda": (_H + r"7\b[\W_]*management.{0,3}s?\s+discussion", _H + r"(?:7a|8|9)\b", 1000),
    },
    "10-Q": {
        "mda": (_H + r"2\b[\W_]*management.{0,3}s?\s+discussion", _H + r"(?:3|4)\b", 1000),
        "rf": (_H + r"1a\b[\W_]*risk\s+factors", _H + r"(?:2|3|4|5|6)\b", 80),
    },
}
_SEC_RE = {f: {k: (re.compile(a, re.I | re.M), re.compile(b, re.I | re.M), n) for k, (a, b, n) in d.items()}
           for f, d in SECTIONS.items()}


def find_section(text: str, start_re: re.Pattern, end_re: re.Pattern, min_len: int) -> tuple[int, int] | None:
    """시작 후보마다 그 뒤 첫 끝 제목까지의 구간 → 가장 긴 것. min_len 미만이면 None."""
    ends = [m.start() for m in end_re.finditer(text)]
    best = None
    for m in start_re.finditer(text):
        i = np.searchsorted(ends, m.end(), side="left")
        if i >= len(ends):
            continue
        span = (m.start(), ends[i])
        if best is None or span[1] - span[0] > best[1] - best[0]:
            best = span
    if best is None or best[1] - best[0] < min_len:
        return None
    return int(best[0]), int(best[1])


def sections(text: str, form: str) -> dict[str, list[int] | None]:
    base = "10-K" if form.startswith("10-K") else "10-Q"
    out = {}
    for k, (a, b, n) in _SEC_RE[base].items():
        sp = find_section(text, a, b, n)
        out[k] = list(sp) if sp else None
    return out


_RE_TOK = re.compile(r"[a-z]{2,}")


def tokens(text: str) -> list[str]:
    return _RE_TOK.findall(text.lower())


def cosine(a: Counter, b: Counter) -> float:
    """단어 빈도 벡터의 코사인 (CMN 2020 Sim_Cosine)."""
    if not a or not b:
        return float("nan")
    small, big = (a, b) if len(a) < len(b) else (b, a)
    dot = sum(v * big.get(k, 0) for k, v in small.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return float(dot / (na * nb))


def jaccard(a, b) -> float:
    """단어 집합의 자카드 (CMN 2020 Sim_Jaccard)."""
    a, b = set(a), set(b)
    if not a or not b:
        return float("nan")
    return len(a & b) / len(a | b)


# ── 이용 가능일 (순수 함수 — 테스트 대상) ──────────────────────────────────────

def avail_session(accept_utc, sessions: pd.DatetimeIndex) -> pd.Series:
    """접수 시각(UTC) → 그 시각보다 엄격히 뒤에 열리는(09:30 ET) 첫 세션. 데이터 밖이면 NaT.
    🔴 09:30 ET 정각 이전 접수만 그날 세션. 09:30 이후(장중·장후)는 다음 세션."""
    ts = pd.to_datetime(pd.Series(accept_utc), utc=True).dt.tz_convert("America/New_York")
    day = ts.dt.tz_localize(None).dt.normalize()
    mins = ts.dt.hour * 60 + ts.dt.minute + ts.dt.second / 60
    first_day = day.where(mins < 9 * 60 + 30, day + pd.Timedelta(days=1))   # 그날 개장 전이면 그날부터
    sess = pd.DatetimeIndex(sessions).normalize()
    pos = sess.searchsorted(first_day.to_numpy("datetime64[ns]"), side="left")
    out = pd.Series(pd.NaT, index=first_day.index, dtype="datetime64[ns]")
    ok = (pos < len(sess)) & first_day.notna().to_numpy()
    out[ok] = sess[pos[ok]]
    return out


def asof_features(P: pd.DataFrame, F: pd.DataFrame, cols, max_age_days: int = 200,
                  date_col: str = "date", avail_col: str = "avail") -> pd.DataFrame:
    """월말 행(date, ticker)에 avail ≤ date 인 가장 최근 공시의 cols 와 나이(age_days)를 붙인다.
    🔴 avail == date 는 보인다(avail 은 이미 '처음 쓸 수 있는 세션'). age > max_age_days 면 결측(공시 중단)."""
    L = P[[date_col, "ticker"]].copy()
    L["_i"] = np.arange(len(L))
    L["ticker"] = L["ticker"].astype(str)
    R = F[["ticker", avail_col, *cols]].dropna(subset=[avail_col]).copy()
    R["ticker"] = R["ticker"].astype(str)
    R = R.sort_values(avail_col).drop_duplicates(["ticker", avail_col], keep="last")
    L = L.sort_values(date_col)
    L[date_col] = pd.to_datetime(L[date_col]).astype("datetime64[ns]")
    R[avail_col] = pd.to_datetime(R[avail_col]).astype("datetime64[ns]")
    M = pd.merge_asof(L, R, left_on=date_col, right_on=avail_col, by="ticker", direction="backward",
                      allow_exact_matches=True)
    M["age_days"] = (M[date_col] - M[avail_col]).dt.days
    stale = M["age_days"] > max_age_days
    M.loc[stale, list(cols)] = np.nan
    M.loc[stale, "age_days"] = np.nan
    M = M.sort_values("_i")
    return M[[*cols, "age_days", avail_col]].reset_index(drop=True)


# ── 티커 → CIK ─────────────────────────────────────────────────────────────

_SUFFIX = re.compile(r"\b(the|inc|incorporated|corp|corporation|co|company|companies|ltd|limited|plc|holdings?|"
                     r"group|n\.?v|s\.?a|l\.?p|llc|trust|international|intl|de|new|del|cl\s+[ab]|class\s+[ab])\b")


def norm_name(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower().replace("&", " and ").replace(".", ""))
    s = _SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def universe() -> pd.DataFrame:
    """패널 티커 + 첫·마지막 월말 + 편출 여부(업종 '(편출)')."""
    P = panel.monthly_panel()
    U = P.groupby("ticker", observed=True)["date"].agg(first="min", last="max").reset_index()
    U["ticker"] = U["ticker"].astype(str)
    raw_sector = panel.load_raw().sector
    U["removed"] = U["ticker"].map(lambda t: raw_sector.get(t) == "(편출)")
    return U


def _wiki_removed_names() -> dict[str, str]:
    import io
    import urllib.request
    req = urllib.request.Request(WIKI_CHANGES, headers={"User-Agent": "Mozilla/5.0 (research script)"})
    ch = pd.read_html(io.StringIO(urllib.request.urlopen(req, timeout=30).read().decode()))[1]
    ch.columns = ["date", "add", "add_name", "rem", "rem_name", "reason"][:len(ch.columns)]
    out = {}
    for t, n in list(zip(ch["add"], ch["add_name"])) + list(zip(ch["rem"], ch["rem_name"])):
        t = str(t).strip().replace(".", "-")
        if re.match(r"^[A-Z-]+$", t) and isinstance(n, str):
            out[t] = n
    return out


def _forms_in_window(sub: pd.DataFrame, a, b) -> int:
    d = pd.to_datetime(sub["filing_date"])
    return int(((d >= pd.Timestamp(a) - pd.Timedelta(days=200)) & (d <= pd.Timestamp(b) + pd.Timedelta(days=30))).sum())


def submissions(cl: Client, cik: int, refresh: bool = False) -> pd.DataFrame:
    """CIK 의 10-K·10-Q (원본만) 목록 — recent + 과거 files 페이지. 압축 캐시."""
    f = EDGAR / "submissions" / f"{cik:010d}.json.gz"
    if f.exists() and not refresh:
        return pd.read_json(f, orient="records", compression="gzip", dtype={"acc": str, "primary": str})
    d = cl.json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    blocks = [d["filings"]["recent"]]
    for x in d["filings"].get("files", []):
        if x.get("filingTo", "9999") >= START:
            blocks.append(cl.json(f"https://data.sec.gov/submissions/{x['name']}"))
    rows = []
    for b in blocks:
        for i, form in enumerate(b["form"]):
            if form in FORMS and b["filingDate"][i] >= START:
                rows.append(dict(cik=cik, form=form, filing_date=b["filingDate"][i],
                                 accept_utc=b["acceptanceDateTime"][i], report_date=b["reportDate"][i] or None,
                                 acc=b["accessionNumber"][i], primary=b["primaryDocument"][i],
                                 name=d.get("name")))
    S = pd.DataFrame(rows, columns=["cik", "form", "filing_date", "accept_utc", "report_date", "acc", "primary", "name"])
    S = S.drop_duplicates("acc")
    f.parent.mkdir(parents=True, exist_ok=True)
    S.to_json(f, orient="records", compression="gzip")
    return S


def map_ciks(cl: Client, U: pd.DataFrame, refresh: bool = False) -> dict:
    """{티커: {cik, method, sec_name}}. method ∈ tickers · name · none."""
    f = EDGAR / "cik_map.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text())
    cur = cl.json("https://www.sec.gov/files/company_tickers.json")
    by_t = {}
    for v in cur.values():
        by_t.setdefault(v["ticker"].upper().replace(".", "-"), (int(v["cik_str"]), v["title"]))
    wiki = _wiki_removed_names()
    out: dict[str, dict] = {}
    need_name = []
    for r in U.itertuples():
        t = r.ticker
        hit = by_t.get(t) or by_t.get(t.replace("-", ""))
        if hit:
            cik, title = hit
            ok = True
            if r.removed:     # 🔴 티커 재사용 점검: 편입 기간에 그 CIK 가 공시했는가
                ok = _forms_in_window(submissions(cl, cik), r.first, r.last) > 0
            if ok:
                out[t] = dict(cik=cik, method="tickers", sec_name=title)
                continue
        need_name.append(t)
    if need_name:
        # SEC 전체 회사명 목록 (이름:CIK:) — 한 번 받는다
        txt = cl.get("https://www.sec.gov/Archives/edgar/cik-lookup-data.txt").content.decode("latin-1")
        names: dict[str, set] = {}
        for ln in txt.splitlines():
            p = ln.rstrip(":").rsplit(":", 1)
            if len(p) == 2 and p[1].isdigit():
                names.setdefault(norm_name(p[0]), set()).add(int(p[1]))
        span = U.set_index("ticker")
        for t in need_name:
            nm = wiki.get(t)
            cands = sorted(names.get(norm_name(nm), set())) if nm else []
            best = None
            for c in cands[:8]:
                n = _forms_in_window(submissions(cl, c), span.at[t, "first"], span.at[t, "last"])
                if n and (best is None or n > best[1]):
                    best = (c, n)
            out[t] = (dict(cik=best[0], method="name", sec_name=nm) if best
                      else dict(cik=None, method="none", sec_name=nm))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=0, ensure_ascii=False))
    return out


def build_index(refresh: bool = False) -> pd.DataFrame:
    cl = Client()
    U = universe()
    M = map_ciks(cl, U, refresh)
    rows = []
    ciks = sorted({v["cik"] for v in M.values() if v["cik"]})
    for i, c in enumerate(ciks):
        rows.append(submissions(cl, c, refresh))
        if i % 100 == 0:
            print(f"  submissions {i}/{len(ciks)}", flush=True)
    S = pd.concat(rows, ignore_index=True).drop_duplicates("acc")
    T = pd.DataFrame([(t, v["cik"]) for t, v in M.items() if v["cik"]], columns=["ticker", "cik"])
    F = T.merge(S, on="cik")
    F.to_parquet(EDGAR / "filings.parquet", index=False)
    n_none = sum(v["method"] == "none" for v in M.values())
    print(f"[index] 티커 {len(U)} → 매핑 {len(U) - n_none} (회사명 {sum(v['method'] == 'name' for v in M.values())}) · "
          f"실패 {n_none} · CIK {len(ciks)} · 공시 {S['acc'].nunique():,}")
    return F


# ── 받기 · 정제 ──────────────────────────────────────────────────────────────

def text_path(cik: int, acc: str) -> Path:
    return EDGAR / "text" / str(int(cik)) / f"{acc}.json.gz"


def process(raw: bytes, form: str) -> dict:
    text = clean_html(raw)
    return {"text": text, "sec": sections(text, form), "n_html": len(raw)}


_CL: Client | None = None


def _worker(job: tuple) -> tuple[str, str | None]:
    """프로세스 하나: 받기 → 정제 → 압축 저장. 반환 (acc, 오류|None)."""
    global _CL
    cik, acc, primary, form, rate = job
    if _CL is None:
        _CL = Client(rate=rate)
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{primary}"
    try:
        raw = _CL.body(url)
        if raw is None:
            return acc, "too_big"
        out = process(raw, form)
        out.update(acc=acc, cik=int(cik), form=form)
        p = text_path(cik, acc)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as fh:
            json.dump(out, fh, ensure_ascii=False)
        tmp.replace(p)
        return acc, None
    except Exception as e:  # noqa: BLE001 — 한 건 실패가 전체를 멈추지 않게 기록만
        return acc, f"{type(e).__name__}: {str(e)[:200]}"


def fetch(workers: int = 8, limit: int | None = None, skip_errors: bool = False):
    user_agent()                                        # 🔴 UA 없으면 여기서 바로 멈춘다
    F = pd.read_parquet(EDGAR / "filings.parquet").drop_duplicates("acc")
    errf = EDGAR / "errors.jsonl"
    bad = set()
    if skip_errors and errf.exists():
        bad = {json.loads(l)["acc"] for l in errf.read_text().splitlines() if l.strip()}
    todo = [r for r in F.itertuples() if not text_path(r.cik, r.acc).exists() and r.acc not in bad]
    todo.sort(key=lambda r: r.filing_date)
    if limit:
        todo = todo[:limit]
    print(f"[fetch] 전체 {len(F):,} · 남은 {len(todo):,} · 프로세스 {workers} · 초당 ≤{RATE:g}", flush=True)
    t0, done, nerr = time.time(), 0, 0
    jobs = [(r.cik, r.acc, r.primary, r.form, RATE / workers) for r in todo]
    with ProcessPoolExecutor(workers) as ex, open(errf, "a") as fe:
        it = iter(jobs)
        pending = set()
        for _ in range(workers * 4):
            j = next(it, None)
            if j:
                pending.add(ex.submit(_worker, j))
        while pending:
            fut = next(as_completed(pending))
            pending.remove(fut)
            acc, err = fut.result()
            done += 1
            if err:
                nerr += 1
                fe.write(json.dumps({"acc": acc, "err": err}) + "\n")
                fe.flush()
            if done % 200 == 0:
                gb = free_gb()
                rate = done / (time.time() - t0)
                print(f"  {done:,}/{len(jobs):,} · 오류 {nerr} · {rate:.1f}건/s · 남은 ~{(len(jobs) - done) / rate / 60:.0f}분 · "
                      f"여유 {gb:.1f}GB · 캐시 {du_gb():.2f}GB", flush=True)
                if gb < MIN_FREE_GB:
                    print(f"[fetch] 🔴 디스크 여유 {gb:.1f}GB < {MIN_FREE_GB}GB — 멈춘다", flush=True)
                    for p in pending:
                        p.cancel()
                    break
            j = next(it, None)
            if j:
                pending.add(ex.submit(_worker, j))
    print(f"[fetch] 끝: {done:,}건 · 오류 {nerr} · {time.time() - t0:.0f}s · 캐시 {du_gb():.2f}GB", flush=True)


def du_gb(path: Path = EDGAR) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e9 if path.exists() else 0.0


def load_text(cik: int, acc: str) -> dict | None:
    p = text_path(cik, acc)
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        return json.load(fh)


# ── 유사도 표 ────────────────────────────────────────────────────────────────

PARTS = ("full", "rf", "mda")


def _counts(d: dict) -> dict[str, Counter | None]:
    t = d["text"]
    out = {"full": Counter(tokens(t))}
    for k in ("rf", "mda"):
        sp = d["sec"].get(k)
        out[k] = Counter(tokens(t[sp[0]:sp[1]])) if sp else None
    return out


def pick_prior(G: pd.DataFrame) -> pd.Series:
    """같은 CIK 공시 G(정렬 무관) → 행마다 비교 대상 acc (없으면 None).
    10-K: 보고기간 끝 300~430일 전 10-K · 10-Q: 330~400일 전 10-Q. 🔴 비교 대상은 먼저 접수된 것만.
    후보가 여럿이면 365일에 가장 가까운 것."""
    G = G.copy()
    ref = pd.to_datetime(G["report_date"]).fillna(pd.to_datetime(G["filing_date"]))
    acc_t = pd.to_datetime(G["accept_utc"], utc=True)
    out = pd.Series([None] * len(G), index=G.index, dtype=object)
    win = {"10-K": (300, 430), "10-Q": (330, 400)}
    for form, (lo, hi) in win.items():
        ix = G.index[G["form"] == form]
        for i in ix:
            dd = (ref[i] - ref[ix]).dt.days
            ok = (dd >= lo) & (dd <= hi) & (acc_t[ix] < acc_t[i])
            if ok.any():
                out[i] = G.loc[(dd[ok] - 365).abs().idxmin(), "acc"]
    return out


def _sims_for_cik(G: pd.DataFrame) -> list[dict]:
    G = G.drop_duplicates("acc").reset_index(drop=True)
    G["prior"] = pick_prior(G)
    cache: dict[str, dict | None] = {}

    def cnt(acc):
        if acc not in cache:
            cik = int(G["cik"].iloc[0])
            d = load_text(cik, acc)
            cache[acc] = _counts(d) if d else None
        return cache[acc]

    rows = []
    for r in G.itertuples():
        row = dict(cik=r.cik, acc=r.acc, form=r.form, prior=r.prior, has_text=False)
        a = cnt(r.acc)
        if a is not None:
            row["has_text"] = True
            row["ntok"] = sum(a["full"].values())
            for k in ("rf", "mda"):
                row[f"has_{k}"] = a[k] is not None
        b = cnt(r.prior) if (a is not None and r.prior) else None
        if b is not None:
            for k in PARTS:
                if a[k] is not None and b[k] is not None:
                    row[f"cos_{k}"] = cosine(a[k], b[k])
                    row[f"jac_{k}"] = jaccard(a[k].keys(), b[k].keys())
                    row[f"dlen_{k}"] = math.log(max(sum(a[k].values()), 1) / max(sum(b[k].values()), 1))
        rows.append(row)
    return rows


def build_sims(workers: int = 6) -> pd.DataFrame:
    F = pd.read_parquet(EDGAR / "filings.parquet")
    S = F.drop_duplicates("acc")
    groups = [g for _, g in S.groupby("cik")]
    rows = []
    t0 = time.time()
    with ProcessPoolExecutor(workers) as ex:
        for i, r in enumerate(ex.map(_sims_for_cik, groups, chunksize=4)):
            rows.extend(r)
            if i % 100 == 0:
                print(f"  sims {i}/{len(groups)} · {time.time() - t0:.0f}s", flush=True)
    X = pd.DataFrame(rows)
    sess = panel.load_raw().sessions
    meta = S[["acc", "filing_date", "accept_utc", "report_date"]]
    X = X.merge(meta, on="acc", how="left")
    X["avail"] = avail_session(X["accept_utc"], sess).to_numpy()
    X.to_parquet(EDGAR / "sims.parquet", index=False)
    print(f"[sims] {len(X):,}건 · 본문 {X['has_text'].mean():.1%} · 비교쌍 {X['cos_full'].notna().mean():.1%} · "
          f"{time.time() - t0:.0f}s")
    return X


def load_sims() -> pd.DataFrame:
    """공시 유사도 + 티커 (여러 티커가 한 CIK 를 쓰면 행이 복제된다 — GOOG/GOOGL 등)."""
    X = pd.read_parquet(EDGAR / "sims.parquet")
    T = pd.read_parquet(EDGAR / "filings.parquet")[["ticker", "acc"]]
    return T.merge(X, on="acc")


def coverage() -> str:
    U = universe()
    M = json.loads((EDGAR / "cik_map.json").read_text())
    X = pd.read_parquet(EDGAR / "sims.parquet") if (EDGAR / "sims.parquet").exists() else None
    lines = []
    meth = Counter(v["method"] for v in M.values())
    rem = U[U["removed"]]["ticker"]
    rem_fail = [t for t in rem if M.get(t, {}).get("method") == "none"]
    cur_fail = [t for t in U[~U["removed"]]["ticker"] if M.get(t, {}).get("method") == "none"]
    lines.append(f"티커 {len(U)} · SEC 티커 파일 {meth['tickers']} · 회사명 {meth['name']} · 실패 {meth['none']}")
    lines.append(f"  편출 종목 {len(rem)} 중 실패 {len(rem_fail)}: {' '.join(sorted(rem_fail))}")
    lines.append(f"  현재 종목 {len(U) - len(rem)} 중 실패 {len(cur_fail)}: {' '.join(sorted(cur_fail))}")
    if X is not None:
        X = X.copy()
        X["year"] = pd.to_datetime(X["filing_date"]).dt.year
        g = X.groupby(["year", "form"]).agg(n=("acc", "size"), text=("has_text", "mean"),
                                            rf=("has_rf", "mean"), mda=("has_mda", "mean"),
                                            pair=("cos_full", lambda s: s.notna().mean()),
                                            pair_rf=("cos_rf", lambda s: s.notna().mean()),
                                            pair_mda=("cos_mda", lambda s: s.notna().mean()))
        lines.append("연도·종류별: 건수 · 본문 · rf 추출 · mda 추출 · 비교쌍(full/rf/mda)")
        for (y, f), r in g.iterrows():
            lines.append(f"  {y} {f:5s} {r.n:5.0f} · {r.text:5.1%} · {r.rf:5.1%} · {r.mda:5.1%} · "
                         f"{r.pair:5.1%}/{r.pair_rf:5.1%}/{r.pair_mda:5.1%}")
    lines.append(f"캐시 {du_gb():.2f}GB · 디스크 여유 {free_gb():.1f}GB")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["index", "fetch", "sims", "coverage"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--skip-errors", action="store_true")
    a = ap.parse_args(argv)
    EDGAR.mkdir(parents=True, exist_ok=True)
    if a.cmd == "index":
        build_index(a.refresh)
    elif a.cmd == "fetch":
        fetch(a.workers, a.limit, a.skip_errors)
    elif a.cmd == "sims":
        build_sims(min(a.workers, 6))
    else:
        print(coverage())


if __name__ == "__main__":
    sys.exit(main())
