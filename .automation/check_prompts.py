#!/usr/bin/env python3
"""프롬프트 문자열이 중간에 끊기는 버그를 잡는다.

── 왜 필요한가 ──────────────────────────────────────────────────────────────
`PROMPT="...긴 한국어 지시문..."` 안에 큰따옴표를 쓰면 문자열이 거기서 끝나고,
뒤에 남은 한국어가 명령어로 실행된다 → `command not found` → 종료코드 127.

같은 버그를 세 번 밟았다:
  ① process-slack-docs.sh  "8/10 오후 2시"        → 슬랙 수집 6일 중단
  ② market-snapshot.sh     "오늘 이렇게 움직였다"  → 시장봇 당일 중단
  ③ (이 검사가 없으면 다음)

**`bash -n` 은 이걸 못 잡는다.** 따옴표 짝이 맞아서 문법적으로는 완전히 정상이고,
의미만 달라지기 때문이다. 그래서 별도 검사가 필요하다.

── 어떻게 잡나 ──────────────────────────────────────────────────────────────
`VAR="` 로 시작하는 대입을 찾아 역슬래시 이스케이프를 존중하며 앞으로 스캔해서
문자열이 실제로 닫히는 위치를 찾는다. 닫는 따옴표 **뒤에 같은 줄에 내용이 더
있으면** 조기 종료다 — 정상이라면 닫는 따옴표는 줄 끝에 온다.

사용법:
  python3 .automation/check_prompts.py [파일...]     # 없으면 .automation/*.sh 전부
종료코드: 문제 있으면 1
"""
import glob
import os
import re
import sys

ASSIGN = re.compile(r'^([A-Z_][A-Z0-9_]*)="', re.M)
# 닫는 따옴표 뒤에 와도 정상인 것: 줄 끝, 주석, 리다이렉션·파이프 같은 셸 문법
OK_AFTER = re.compile(r'^\s*(#.*)?$|^\s*(2>&1|[|)&;<>]|>>?\s)')


def find_close(text, start):
    """start(여는 따옴표 다음)부터 닫는 따옴표 위치를 찾는다. 없으면 None.

    `$( ... )` 안은 따옴표 규칙이 새로 시작되는 별개 문맥이라 통째로 건너뛴다.
    안 그러면 `SCRIPT_DIR="$(cd "$(dirname ...)" && pwd)"` 같은 정상 코드를
    오탐한다.
    """
    i = start
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "$" and text.startswith("$(", i):
            depth, i = 1, i + 2
            while i < len(text) and depth:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                i += 1
            continue
        if c == '"':
            return i
        i += 1
    return None


def check(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()

    problems = []
    for m in ASSIGN.finditer(text):
        var = m.group(1)
        close = find_close(text, m.end())
        if close is None:
            problems.append((var, text[:m.start()].count("\n") + 1,
                             "닫는 따옴표가 없다"))
            continue

        line_end = text.find("\n", close)
        if line_end == -1:
            line_end = len(text)
        tail = text[close + 1:line_end]

        if tail.strip() and not OK_AFTER.match(tail):
            lineno = text[:close].count("\n") + 1
            problems.append((var, lineno, f"문자열이 여기서 끊긴다 → 뒤에 남은 것: {tail.strip()[:50]!r}"))

    return problems


def main():
    targets = sys.argv[1:] or sorted(glob.glob(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "*.sh")))
    bad = 0
    for p in targets:
        for var, line, why in check(p):
            print(f"🔴 {os.path.relpath(p)}:{line}  ${var} — {why}")
            bad += 1
    if bad:
        print(f"\n{bad}건. 큰따옴표를 작은따옴표로 바꾸거나 \\\" 로 이스케이프할 것.")
        return 1
    print(f"✅ 프롬프트 문자열 정상 — {len(targets)}개 파일 검사")
    return 0


if __name__ == "__main__":
    sys.exit(main())
