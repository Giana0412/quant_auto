#!/usr/bin/env python3
"""파이프라인 브리지 — 운영 코드를 **복사하지 않고 그대로 호출**한다.

── 왜 서브프로세스인가 ───────────────────────────────────────────────────
`market_metrics` 와 `news_sentiment` 는 `gs_quant` 를 끌어온다. 그걸 이 프로젝트
venv 에 깔면 무겁고, 피하려고 사전을 복사해 오면 **운영본과 갈라진다.**

갈라지면 비교가 무의미해진다 — 우리가 이기려는 건 "예전에 복사해둔 사전"이 아니라
**지금 매일 돌고 있는 그 사전**이다. 그래서 파이프라인 venv 를 그대로 호출해
JSON 으로 주고받는다. 느리지만 한 번만 부르면 되고, 무엇보다 **거짓말을 안 한다.**
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/gyuhyeongkim/orca/projects/quant_auto")
PY = ROOT / ".automation" / ".venv" / "bin" / "python"


def _run(code, stdin=""):
    if not PY.exists():
        raise SystemExit(f"파이프라인 venv 를 못 찾았다: {PY}")
    r = subprocess.run([str(PY), "-c", code], input=stdin, cwd=str(ROOT),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"파이프라인 호출 실패:\n{r.stderr[-800:]}")
    # 스크립트가 경고를 stdout 에 흘릴 수 있어 **마지막 JSON 줄**만 취한다
    for line in reversed(r.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith(("{", "[")):
            return json.loads(line)
    raise SystemExit(f"JSON 을 못 찾았다. stdout 끝:\n{r.stdout[-500:]}")


def universe():
    """{티커: {name, sector, ...}} — 파이프라인이 쓰는 그 유니버스."""
    return _run(
        "import sys,json,warnings;warnings.filterwarnings('ignore');"
        "sys.path.insert(0,'.automation');"
        "from market_metrics import screen_universe;"
        "print(json.dumps(screen_universe()))")


def noise_patterns():
    """클릭베이트 필터 정규식 목록."""
    return _run(
        "import sys,json,warnings;warnings.filterwarnings('ignore');"
        "sys.path.insert(0,'.automation');"
        "from news_sentiment import NOISE;"
        "print(json.dumps(NOISE))")


def score_titles(titles):
    """헤드라인 목록 → [(점수, 매칭수)]. 운영 중인 score_text 를 그대로 쓴다."""
    code = (
        "import sys,json,warnings;warnings.filterwarnings('ignore');"
        "sys.path.insert(0,'.automation');"
        "from news_sentiment import score_text;"
        "ts=json.load(sys.stdin);"
        "print(json.dumps([[score_text(t)[0],score_text(t)[1]] for t in ts]))")
    return _run(code, stdin=json.dumps(titles))


if __name__ == "__main__":
    u = universe()
    n = noise_patterns()
    s = score_titles(["Apple beats earnings estimates, raises guidance",
                      "Tesla downgraded on weak demand concerns",
                      "Company announces quarterly results"])
    print(f"유니버스 {len(u)}종목 · 잡음필터 {len(n)}개")
    print(f"점수 테스트: {s}  ← [호재+, 악재-, 중립0] 이어야 정상")
