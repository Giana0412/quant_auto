#!/usr/bin/env python3
"""vault의 schema 규칙 위반을 찾아 보고한다. 고치지는 않는다.

260811 싱크에서 정의한 세 오퍼레이션(ingest / query / lint) 중 lint.
자동 수정을 하지 않는 이유: 사람이 의도해서 만든 예외를 지워버릴 수 있다.
무엇이 어긋났는지 목록만 내고, 고칠지는 사람이 정한다.

규칙은 상상해서 만든 것이 아니라 2026-08-10~12 실측에서 실제로 발견된 것들이다
(vault/01-architecture/전체-구조도.md §4~§6).

사용법:
  python3 .automation/wiki_lint.py            # 전체 검사
  python3 .automation/wiki_lint.py --rule L2  # 특정 규칙만
  python3 .automation/wiki_lint.py --strict   # 위반이 있으면 종료코드 1
"""

import os
import re
import sys
from collections import defaultdict
from datetime import date

VAULT_DIR = os.environ.get(
    "VAULT_DIR", "/Users/gyuhyeongkim/orca/projects/obsidian_test"
)
ROOT = os.path.join(VAULT_DIR, "vault")

# 자동 수집·자동 생성 영역. 사람이 링크를 걸지 않는 게 정상이므로
# 고아 문서(L4) 검사에서 제외한다.
RAW_DIRS = ("vault/05-slack", "vault/06-docs/01-전사본")

# 코드블록 안의 예시 표기는 검사 대상이 아니다 (`[[링크]]` 같은 설명용 표기).
FENCE = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")

WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
# Obsidian 태그: 앞이 줄머리/공백/여는괄호여야 하고, 문자·숫자·_·-·/ 로 이뤄진다.
TAG = re.compile(r"(?:(?<=^)|(?<=[\s(\[]))#([가-힣A-Za-z0-9_/-]+)", re.M)
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def rel(path):
    return os.path.relpath(path, VAULT_DIR)


def strip_code(text):
    """코드블록·백틱 안의 내용을 지우되 **줄 수는 그대로 유지**한다.

    그냥 지우면 뒤쪽 내용의 줄 번호가 앞으로 당겨져서 보고된 위치가 실제와
    어긋난다. 지운 자리를 같은 개수의 개행으로 채워 줄 번호를 보존한다.
    """
    def blank(m):
        return "\n" * m.group(0).count("\n")

    return INLINE_CODE.sub(blank, FENCE.sub(blank, text))


def load_docs():
    docs = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(".md"):
                p = os.path.join(dirpath, fn)
                with open(p, encoding="utf-8") as f:
                    docs[p] = f.read()
    return docs


def frontmatter(text):
    m = FRONTMATTER.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).split("\n"):
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def line_of(text, index):
    return text.count("\n", 0, index) + 1


# ---------------------------------------------------------------- 규칙들

def L1_broken_links(docs):
    """깨진 위키링크가 없을 것."""
    by_name = defaultdict(list)
    for p in docs:
        by_name[os.path.splitext(os.path.basename(p))[0]].append(p)

    out = []
    for p, text in docs.items():
        body = strip_code(text)
        for m in WIKILINK.finditer(body):
            tgt = m.group(1).strip()
            base = os.path.splitext(os.path.basename(tgt))[0]
            ok = base in by_name
            if "/" in tgt:  # 상대경로 링크는 경로까지 맞아야 한다
                cand = os.path.normpath(os.path.join(os.path.dirname(p), tgt))
                ok = ok and (os.path.exists(cand + ".md") or os.path.exists(cand))
            if not ok:
                out.append((rel(p), line_of(body, m.start()), f"[[{tgt}]] 대상 없음"))
    return out


def L2_accidental_tags(docs):
    """결정 번호 표기가 태그로 오인식되지 않을 것.

    '결정 #9는 ~' 처럼 쓰면 한글 조사가 붙어 Obsidian이 진짜 태그로 등록한다.
    (#1, #12 처럼 숫자만이면 태그가 되지 않는다 — 태그는 비숫자 문자를 최소
    하나 포함해야 한다.) 태그 창이 #9는, #3과 같은 항목으로 채워진다.
    """
    out = []
    for p, text in docs.items():
        body = strip_code(text)
        for m in TAG.finditer(body):
            tag = m.group(1)
            if tag.isdigit():
                continue  # 태그로 인식되지 않음 — 문제 없다
            if re.match(r"^\d+[가-힣]", tag):
                out.append(
                    (rel(p), line_of(body, m.start()),
                     f"#{tag} — 번호 표기가 태그가 됐다. '{tag[:len(tag)-len(tag.lstrip('0123456789'))]}번' 처럼 쓰거나 백틱으로 감쌀 것")
                )
    return out


def L3_created(docs):
    """모든 문서에 created 가 있을 것."""
    out = []
    for p, text in docs.items():
        fm = frontmatter(text)
        if not fm:
            out.append((rel(p), 1, "프론트매터 자체가 없음"))
        elif "created" not in fm:
            out.append((rel(p), 1, "created 누락"))
    return out


def L5_stale_updated(docs):
    """고쳐진 문서에는 updated 가 있을 것.

    처음에는 '모든 문서에 updated 필수'로 만들었더니 50개 중 42개가 걸려
    규칙이 쓸모없어졌다. 회의록처럼 한 번 쓰고 안 고치는 문서에는 updated 가
    없는 게 정상이기 때문이다. 그래서 git 이력을 근거로 바꿨다 —
    **실제로 두 번 이상 커밋된 문서인데 updated 가 없거나 옛날 값이면** 위반이다.
    """
    import subprocess

    out = []
    for p, text in docs.items():
        fm = frontmatter(text)
        try:
            log = subprocess.run(
                ["git", "log", "--format=%ad", "--date=short", "--", rel(p)],
                cwd=VAULT_DIR, capture_output=True, text=True, timeout=15,
            ).stdout.split()
        except Exception:
            continue
        if len(log) < 2:
            continue  # 한 번만 커밋된 문서 — 고쳐진 적 없다
        last_commit = log[0]
        if "updated" not in fm:
            out.append((rel(p), 1, f"{len(log)}회 수정됐는데 updated 없음 (최근 {last_commit})"))
        elif fm["updated"][:10] < last_commit:
            out.append((rel(p), 1, f"updated={fm['updated'][:10]} 인데 실제 최근 수정은 {last_commit}"))
    return out


def L4_orphans(docs):
    """어느 문서에서도 링크되지 않은 문서가 없을 것.

    검색으로만 도달 가능한 문서는 사실상 묻힌다. 다만 자동 수집 영역(raw)은
    사람이 링크를 걸지 않는 게 정상이라 제외한다.
    """
    linked = set()
    for p, text in docs.items():
        for m in WIKILINK.finditer(strip_code(text)):
            linked.add(os.path.splitext(os.path.basename(m.group(1).strip()))[0])

    out = []
    for p in docs:
        if rel(p).startswith(RAW_DIRS):
            continue
        name = os.path.splitext(os.path.basename(p))[0]
        if name not in linked:
            out.append((rel(p), 1, "아무 문서도 이 문서를 링크하지 않음"))
    return out


def L7_stale(docs):
    """review_by 가 지난 문서를 보고한다 (오래된 문서 정리 장치)."""
    today = date.today()
    out = []
    for p, text in docs.items():
        v = frontmatter(text).get("review_by")
        if not v:
            continue
        try:
            due = date.fromisoformat(v)
        except ValueError:
            out.append((rel(p), 1, f"review_by 값을 날짜로 못 읽음: {v}"))
            continue
        if due < today:
            out.append((rel(p), 1, f"검토 기한 지남 ({v}, {(today - due).days}일 경과)"))
    return out


RULES = [
    ("L1", "깨진 위키링크", L1_broken_links),
    ("L2", "번호 표기가 태그로 오인식", L2_accidental_tags),
    ("L3", "프론트매터 created 누락", L3_created),
    ("L4", "고아 문서 (아무도 링크하지 않음)", L4_orphans),
    ("L5", "고쳐졌는데 updated 가 없거나 옛날 값", L5_stale_updated),
    ("L7", "검토 기한이 지난 문서", L7_stale),
]


def main():
    only = None
    if "--rule" in sys.argv:
        only = sys.argv[sys.argv.index("--rule") + 1].upper()

    docs = load_docs()
    print(f"vault 문서 {len(docs)}개 검사\n")

    total = 0
    for code, title, fn in RULES:
        if only and code != only:
            continue
        hits = fn(docs)
        total += len(hits)
        mark = "✅" if not hits else "⚠️"
        print(f"{mark} {code} {title} — {len(hits)}건")
        for path, line, msg in sorted(hits):
            print(f"     {path}:{line}  {msg}")
        print()

    print(f"합계 {total}건. 이 도구는 보고만 하고 고치지 않는다.")
    if total and "--strict" in sys.argv:
        sys.exit(1)


if __name__ == "__main__":
    main()
