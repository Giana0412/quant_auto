#!/usr/bin/env python3
"""에이전트 리뷰 — 모델 북 종목에 TradingAgents 의 **세컨드 오피니언**을 붙인다.

── 무엇인가 ──────────────────────────────────────────────────────────────
TradingAgents(github.com/TauricResearch/TradingAgents, v0.7.1 고정)는 종목 하나를
LLM 애널리스트(기술·뉴스·펀더멘털) → 강세/약세 토론 → 트레이더 → 리스크팀 →
PM 순서로 돌려 5단계 등급(Buy/Overweight/Hold/Underweight/Sell)을 낸다.
우리 북은 정량 스크리닝(market_metrics.py)이 고른다. 이 스크립트는 그 북의
종목을 TradingAgents 에 넣고 등급과 요약을 브리핑에 옆으로 붙인다.

── 🔴 북을 바꾸지 않는다 ───────────────────────────────────────────────────
2026-11-06 결정: **세컨드 오피니언으로만 쓴다.** 검증되지 않은 신호가 실제 북을
바꾸면 안 된다 — 이 레포가 백테스트 숫자에 대해 내내 지켜 온 원칙과 같다
(§README "백테스트 숫자를 믿지 말 것"). 대회가 끝나는 날(11/13, 추정)까지
남은 거래일이 약 5일이라 그 사이에 검증될 수도 없다.
대신 **등급을 매일 기록하고 스스로 채점한다**(paper_track 과 같은 정신). 북은
전부 롱이므로 시험할 질문은 하나다: *북 안에서 에이전트가 약세라고 한 종목이
강세라고 한 종목보다 실제로 못했나?* → `score` 가 그 차이를 낸다.

── 왜 venv 를 따로 두나 ─────────────────────────────────────────────────────
langchain·langgraph 가 줄줄이 따라온다. gs-quant 가 사는 .venv 에 섞으면 한쪽
업그레이드가 다른 쪽을 깰 수 있다. 그래서 .automation/.venv-ta 에 따로 둔다.
이 스크립트는 market_metrics 를 임포트하지 않는다 — 북은 paper_track 이 남긴
book-log.jsonl 에서 읽는다(같은 북을 두 번 계산하지 않는다).

── LLM 은 구독(claude -p)으로 돈다 ─────────────────────────────────────────
기본 백엔드는 claude_cli — 로그인된 claude CLI 를 호출 단위로 띄운다(§claude_cli_llm.py,
약관상 허용되는 방식과 그 이유도 거기 있다). 과금은 없지만 **구독 사용 한도**를 쓴다.
종목당 LLM 호출이 수십 번이다. **같은 기준일·종목은 다시 돌리지 않는다** — 07:30 백업
체인이나 손으로 다시 돌려도 한도를 두 번 쓰지 않게.
API 키로 돌리고 싶으면 TA_BACKEND=anthropic + .automation/.anthropic.env.

사용:
  .automation/.venv-ta/bin/python .automation/agent_review.py run          # 최신 북 전부
  .automation/.venv-ta/bin/python .automation/agent_review.py run --tickers GILD VMC
  .automation/.venv-ta/bin/python .automation/agent_review.py score
  .automation/.venv-ta/bin/python .automation/agent_review.py brief        # md 만 다시 쓰기

종료코드(run): 0 성공 또는 할 일 없음 · 1 전부 실패 · 2 LLM 백엔드 없음 · 3 북이 오래됨
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
MARKET = ROOT / "personal" / "10-market"
BOOK_LOG = MARKET / "_paper" / "book-log.jsonl"
OUT = MARKET / "_agents"
LOG = OUT / "agent-log.jsonl"
KEY_FILE = ROOT / ".automation" / ".anthropic.env"
KST = ZoneInfo("Asia/Seoul")

BACKEND = os.environ.get("TA_BACKEND", "claude_cli")   # claude_cli(구독) | anthropic(API 키)
# 모델은 환경변수로 바꿀 수 있다. 기본값은 TradingAgents 카탈로그에 있는 이름이다
# (카탈로그에 없으면 경고가 뜬다). quick = 애널리스트·토론·트레이더, deep = 매니저.
QUICK = os.environ.get("TA_QUICK_LLM", "claude-sonnet-5")
DEEP = os.environ.get("TA_DEEP_LLM", "claude-opus-5-5")
# social(StockTwits·Reddit)은 뺐다 — 느리고, 중소형주는 글이 거의 없어 빈 보고서가 나온다.
ANALYSTS = tuple(os.environ.get("TA_ANALYSTS", "market,news,fundamentals").split(","))

BULL = {"Buy", "Overweight"}
BEAR = {"Underweight", "Sell"}

# 🔴 채점은 기준일 **다음 거래일 종가**에 진입했다고 가정한다. 체인은 06:00 KST
# (미 동부 전날 16~17시)에 돌아 기준일 종가 뒤에 나온 뉴스까지 읽을 수 있고,
# 사람이 이 의견을 보고 움직일 수 있는 것도 다음 세션부터다. 기준일 종가로
# 진입시키면 의견이 이미 본 움직임을 성적으로 세게 된다. paper_track 은 기준일
# 종가 진입이라 두 숫자를 그대로 비교하면 안 된다.
ENTRY_LAG = 1


# ── 공통 ─────────────────────────────────────────────────────────────────

def _load_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    if KEY_FILE.exists():
        for line in KEY_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def _append(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def latest_book() -> dict | None:
    books = [r for r in _read_jsonl(BOOK_LOG) if r.get("kind") == "defensive" and r.get("book")]
    return max(books, key=lambda r: (r["date"], r.get("run_date", ""))) if books else None


def reviewed(day: str) -> dict[str, dict]:
    """기준일 day 에 이미 등급이 나온 종목. REVIEW(등급 못 읽음)·실패는 다시 돌린다."""
    return {r["ticker"]: r for r in _read_jsonl(LOG)
            if r.get("date") == day and r.get("rating") not in (None, "REVIEW")}


# ── 한 종목 (자식 프로세스) ────────────────────────────────────────────────
# 종목마다 프로세스를 따로 띄운다. 스레드는 상한에서 죽일 수 없고, 한 종목이
# LLM 응답을 기다리며 매달리면 나머지까지 붙잡는다 — 이 레포가 "무엇도 영원히
# 매달려선 안 된다"(§evening-chain.sh)를 배운 방식 그대로다.

def cmd_one(ticker: str, day: str, out_path: str) -> int:
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    if BACKEND == "claude_cli":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import claude_cli_llm
        claude_cli_llm.install()

    cfg = DEFAULT_CONFIG.copy()
    cfg.update(
        llm_provider=BACKEND,
        quick_think_llm=QUICK,
        deep_think_llm=DEEP,
        output_language="Korean",       # 토론은 영어로 하고 보고서·결정만 한국어로 낸다
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        results_dir=str(OUT / "results"),
        # 기억 로그를 personal/ 아래에 둔다 — 지난 결정을 채점하고 반성문을 다음
        # 실행에 넘기는 TradingAgents 자체 기능이 여기서 누적된다.
        memory_log_path=str(OUT / "memory.md"),
    )
    t0 = time.time()
    ta = TradingAgentsGraph(selected_analysts=ANALYSTS, config=cfg)
    state, rating = ta.propagate(ticker, day)
    report = ta.save_reports(state, ticker)

    decision = state.get("final_trade_decision", "") or ""
    fields = {}
    for part in decision.split("\n\n"):
        if part.startswith("**") and "**:" in part:
            k, v = part[2:].split("**:", 1)
            fields[k.strip()] = v.strip()
    res = dict(
        ticker=ticker, rating=rating,
        summary=fields.get("Executive Summary", decision[:400]),
        price_target=fields.get("Price Target"),
        horizon=fields.get("Time Horizon"),
        report=str(Path(report).relative_to(ROOT)) if str(report).startswith(str(ROOT)) else str(report),
        secs=round(time.time() - t0),
    )
    Path(out_path).write_text(json.dumps(res, ensure_ascii=False))
    return 0


def _spawn(ticker: str, day: str, timeout: int) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out = tf.name
    t0 = time.time()
    try:
        p = subprocess.run(
            [sys.executable, __file__, "one", ticker, day, out],
            capture_output=True, text=True, timeout=timeout,
        )
        if p.returncode == 0 and Path(out).stat().st_size:
            return json.loads(Path(out).read_text())
        # 마지막 줄은 LangGraph 의 'During task with name ...' 꼬리표라 원인이 아니다.
        # 예외 이름이 박힌 마지막 줄(인증·한도·네트워크)을 원인으로 남긴다.
        lines = (p.stderr or p.stdout).strip().splitlines()
        cause = next((l for l in reversed(lines) if "Error" in l or "Exception" in l),
                     lines[-1] if lines else "출력 없음")
        return dict(ticker=ticker, rating=None, error=f"rc={p.returncode} {cause.strip()[:200]}",
                    secs=round(time.time() - t0))
    except subprocess.TimeoutExpired:
        return dict(ticker=ticker, rating=None, error=f"{timeout}초 초과", secs=timeout)
    finally:
        Path(out).unlink(missing_ok=True)


# ── run ──────────────────────────────────────────────────────────────────

def cmd_run(tickers: list[str] | None, jobs: int, timeout: int, max_age: int) -> int:
    if BACKEND == "anthropic" and not _load_key():
        print(f"[에이전트] ANTHROPIC_API_KEY 없음 — {KEY_FILE.relative_to(ROOT)} 에 넣는다. 건너뜀")
        return 2
    if BACKEND == "claude_cli":
        claude = Path(os.environ.get("CLAUDE_BIN", Path.home() / ".local/bin/claude"))
        if not claude.exists():
            print(f"[에이전트] claude CLI 없음 ({claude}) — 건너뜀")
            return 2

    book = latest_book()
    if tickers:
        day = book["date"] if book else date.today().isoformat()
        weights = {t: (book or {}).get("book", {}).get(t) for t in tickers}
    else:
        if not book:
            print("[에이전트] 북 기록 없음 (paper_track.py record 가 아직 안 돌았다)")
            return 3
        # 🔴 오늘 체인에서 기록된 북인지 확인한다. 기록이 빠졌는데 지난주 북으로
        # 돌면, 브리핑에 '오늘 북에 대한 의견'처럼 실린다. 날짜는 run_date(언제
        # 돌았나)로 본다 — date 는 기준 종가라 주말엔 원래 며칠 전이다.
        age = (date.today() - date.fromisoformat(book.get("run_date", book["date"]))).days
        if age > max_age:
            print(f"[에이전트] 최신 북이 {age}일 전 기록 ({book.get('run_date')}) — 오래됨")
            return 3
        day, weights = book["date"], book["book"]

    done = reviewed(day)
    todo = [t for t in weights if t not in done]
    if done:
        print(f"[에이전트] 기준일 {day}: {len(done)}종목은 이미 있음 — 다시 안 돌린다")
    if not todo:
        write_brief(day)
        return 0

    print(f"[에이전트] 기준일 {day} · {len(todo)}종목 · {BACKEND} {QUICK}/{DEEP} · 동시 {jobs}")
    ok = 0
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        for res in ex.map(lambda t: _spawn(t, day, timeout), todo):
            res.update(date=day, run_date=date.today().isoformat(),
                       weight=weights.get(res["ticker"]), backend=BACKEND, quick=QUICK, deep=DEEP,
                       analysts=list(ANALYSTS))
            _append(LOG, res)
            if res.get("rating"):
                ok += 1
                print(f"  {res['ticker']:6} {res['rating']:11} ({res['secs']}초)")
            else:
                print(f"  {res['ticker']:6} 🔴 실패 — {res.get('error')}")
    write_brief(day)
    print(f"[에이전트] {ok}/{len(todo)} 성공")
    return 0 if ok else 1


# ── brief: daily-conclusion 이 읽는 파일 ───────────────────────────────────

def _clip(text: str, limit: int = 300) -> str:
    """문장 중간에서 자르지 않는다 — '50 SMA(' 처럼 끊기면 읽는 사람이 뜻을 놓친다."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind("다. "), cut.rfind(". "))
    return (cut[:end + 1] if end > limit // 2 else cut.rstrip()) + " …"


def write_brief(day: str) -> Path | None:
    rows = reviewed(day)
    if not rows:
        return None
    chain = os.environ.get("CHAIN_DATE") or datetime.now(KST).strftime("%y%m%d")
    path = MARKET / "data" / f"{chain}-에이전트의견.md"
    order = {"Buy": 0, "Overweight": 1, "Hold": 2, "Underweight": 3, "Sell": 4}
    lines = [
        f"# 에이전트 의견 (TradingAgents) — 기준 종가 {day}",
        "",
        "🔴 검증 안 된 LLM 의견이다. 모델 북을 바꾸는 근거로 쓰지 않는다 (세컨드 오피니언 전용).",
        f"모델: {BACKEND} {QUICK} / {DEEP} · 애널리스트: {', '.join(ANALYSTS)}",
        "",
    ]
    for r in sorted(rows.values(), key=lambda r: (order.get(r["rating"], 9), r["ticker"])):
        w = f"{r['weight'] * 100:.0f}%" if r.get("weight") else "북 밖"
        flag = " ⚠️북과 반대" if r["rating"] in BEAR and r.get("weight") else ""
        lines.append(f"- **{r['ticker']}** ({w}) — {r['rating']}{flag}")
        lines.append(f"  - {_clip(str(r.get('summary', '')))}")
        if r.get("report"):
            lines.append(f"  - 보고서: `{r['report']}`")
    lines += ["", f"누적 성적: {score_line()}"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    print(f"[에이전트] {path.relative_to(ROOT)} 작성")
    return path


# ── score ────────────────────────────────────────────────────────────────

def _scored() -> list[dict]:
    rows = [r for r in _read_jsonl(LOG) if r.get("rating") not in (None, "REVIEW")]
    # 같은 날·종목이 여러 줄이면 마지막 것만 (재실행)
    rows = list({(r["date"], r["ticker"]): r for r in rows}.values())
    if not rows:
        return []
    import pandas as pd
    import yfinance as yf

    syms = sorted({r["ticker"] for r in rows} | {"ACWI"})
    start = min(r["date"] for r in rows)
    px = yf.download(syms, start=start, auto_adjust=True, progress=False)["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame(syms[0])
    out = []
    for r in rows:
        if r["ticker"] not in px or "ACWI" not in px:
            continue
        after = px.index[px.index.date > date.fromisoformat(r["date"])]
        if len(after) < ENTRY_LAG + 1:      # 진입일 다음 종가가 하나는 있어야 잰다
            continue
        t0, t1 = after[ENTRY_LAG - 1], px.index[-1]
        s, b = px[r["ticker"]], px["ACWI"]
        if pd.isna(s.get(t0)) or pd.isna(s.get(t1)):
            continue
        ret = s[t1] / s[t0] - 1
        alpha = ret - (b[t1] / b[t0] - 1)
        out.append(dict(r, ret=ret, alpha=alpha, entry=str(t0.date()), days=int((px.index > t0).sum())))
    return out


def _group(rating: str) -> str:
    return "강세" if rating in BULL else "약세" if rating in BEAR else "중립"


def score_line() -> str:
    try:
        s = _scored()
    except Exception as e:                      # 채점 실패가 브리핑을 막으면 안 된다
        return f"채점 실패 ({type(e).__name__})"
    if not s:
        return "아직 없음 (진입 다음 종가가 쌓여야 잰다)"
    parts = []
    for g in ("강세", "중립", "약세"):
        a = [x["alpha"] for x in s if _group(x["rating"]) == g]
        if a:
            parts.append(f"{g} {len(a)}건 평균 {sum(a) / len(a) * 100:+.2f}%p")
    return " · ".join(parts) + f" (ACWI 대비, n={len(s)} — 표본이 작아 의미 없음)"


def cmd_score(detail: bool) -> int:
    s = _scored()
    if not s:
        print("채점할 기록 없음")
        return 0
    print(f"[에이전트 채점] {len(s)}건 · 진입 = 기준일 다음 종가 · ACWI 대비\n")
    for g in ("강세", "중립", "약세"):
        xs = [x for x in s if _group(x["rating"]) == g]
        if not xs:
            continue
        a = [x["alpha"] for x in xs]
        hit = sum(v > 0 for v in a) / len(a)
        print(f"  {g:2} {len(xs):3}건  평균 초과 {sum(a) / len(a) * 100:+6.2f}%p  적중 {hit:.0%}")
    bull = [x["alpha"] for x in s if _group(x["rating"]) == "강세"]
    bear = [x["alpha"] for x in s if _group(x["rating"]) == "약세"]
    if bull and bear:
        spread = sum(bull) / len(bull) - sum(bear) / len(bear)
        print(f"\n  강세−약세 스프레드 {spread * 100:+.2f}%p  ← 양수여야 에이전트가 북 안에서 가려낸다")
    print("\n  🔴 날짜가 며칠뿐이면 같은 장세의 같은 베팅이다. 건수가 아니라 고유 기준일 수를 볼 것: "
          f"{len({x['date'] for x in s})}일")
    if detail:
        print()
        for x in sorted(s, key=lambda x: (x["date"], x["ticker"])):
            print(f"  {x['date']} {x['ticker']:6} {x['rating']:11} 진입 {x['entry']} "
                  f"{x['days']}일  수익 {x['ret'] * 100:+6.2f}%  초과 {x['alpha'] * 100:+6.2f}%p")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--tickers", nargs="+")
    r.add_argument("--jobs", type=int, default=2, help="동시 종목 수 — 구독 한도를 같이 쓰므로 낮게")
    r.add_argument("--timeout", type=int, default=900, help="종목당 상한(초)")
    r.add_argument("--max-age", type=int, default=1, help="북 기록이 며칠 지나면 오래됐다고 볼지")
    o = sub.add_parser("one")
    o.add_argument("ticker"); o.add_argument("day"); o.add_argument("out")
    sc = sub.add_parser("score")
    sc.add_argument("--detail", action="store_true")
    b = sub.add_parser("brief")
    b.add_argument("--date")
    a = ap.parse_args()

    if a.cmd == "run":
        return cmd_run([t.upper() for t in a.tickers] if a.tickers else None,
                       a.jobs, a.timeout, a.max_age)
    if a.cmd == "one":
        if BACKEND == "anthropic":
            _load_key()
        return cmd_one(a.ticker, a.day, a.out)
    if a.cmd == "score":
        return cmd_score(a.detail)
    if a.cmd == "brief":
        day = a.date or (latest_book() or {}).get("date")
        return 0 if day and write_brief(day) else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
