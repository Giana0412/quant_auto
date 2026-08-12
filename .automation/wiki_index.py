#!/usr/bin/env python3
"""vault/index/ 의 목차를 자동 생성한다.

260811 싱크에서 이준범이 지적한 "index 설계"가 빠져 있던 부분. 사람이 손으로
관리하는 목차는 반드시 낡는다 — 파일에서 유도할 수 있는 것만 자동으로 만든다.

이 폴더의 파일은 매번 통째로 덮어쓴다. 손으로 고치지 말 것.
"""

import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime

VAULT_DIR = os.environ.get(
    "VAULT_DIR", "/Users/gyuhyeongkim/orca/projects/obsidian_test"
)
INDEX_DIR = os.path.join(VAULT_DIR, "vault/index")
TODAY = date.today().isoformat()

KINDS = [
    ("전사본", "vault/raw/transcripts"),
    ("정리본", "vault/wiki/05-meetings/정리본"),
    ("결정사항", "vault/wiki/05-meetings/결정사항"),
]
# 260811-옵시디언방향성싱크-정리본.md → ('260811', '옵시디언방향성싱크', '정리본')
NAME = re.compile(r"^(\d{6})-(.+)-(전사본|정리본|결정사항)$")


FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def summary_of(path, limit=70):
    """문서의 한 줄 요약. frontmatter 의 purpose 를 우선 쓰고, 없으면 본문 첫 문장.

    카파시 원문: index 는 "each page listed with a link, **a one-line summary**".
    요약이 없으면 에이전트가 인덱스만 보고 어느 페이지를 열지 판단할 수 없어
    결국 전부 열어봐야 한다 — 인덱스를 두는 의미가 사라진다.
    """
    try:
        text = open(path, encoding="utf-8").read()
    except Exception:
        return ""

    m = FM.match(text)
    if m:
        for line in m.group(1).split("\n"):
            if line.startswith("purpose:"):
                return line.split(":", 1)[1].strip().strip('"')[:limit]
        body = text[m.end():]
    else:
        body = text

    def clean(t):
        t = re.sub(r"\[\[([^\]|]+)(\|[^\]]*)?\]\]", r"\1", t)   # 링크 표기 제거
        return re.sub(r"\*\*|__|`", "", t).strip()[:limit]

    first_item = ""
    for line in body.split("\n"):
        line = line.strip()
        if not line or line.startswith(("#", ">", "|", "`", "!", "---")):
            continue
        # 목록 항목은 차선책으로 남겨둔다 — 결정사항 문서처럼 본문이 전부
        # 목록인 경우가 있어서, 산문이 하나도 없으면 첫 항목이라도 쓴다
        m2 = re.match(r"^[-*+]\s+(.*)|^\d+\.\s+(.*)", line)
        if m2:
            if not first_item:
                first_item = clean(m2.group(1) or m2.group(2) or "")
            continue
        return clean(line)
    return first_item


def header(title, purpose):
    return (
        f"---\ncreated: 2026-08-12\nupdated: {TODAY}\n"
        f"purpose: {purpose}\n---\n\n# {title}\n\n"
        "> 이 문서는 `.automation/wiki_index.py` 가 자동 생성한다. **손으로 고치지 말 것** "
        "— 다음 실행에서 덮어써진다.\n\n"
    )


def build_meetings():
    """회의별로 3종 문서가 갖춰졌는지 한눈에 보이는 목차."""
    found = defaultdict(dict)
    for kind, folder in KINDS:
        d = os.path.join(VAULT_DIR, folder)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".md"):
                continue
            m = NAME.match(fn[:-3])
            if m:
                yymmdd, topic, k = m.groups()
                found[(yymmdd, topic)][k] = fn[:-3]

    lines = [header("회의 목차", "회의별 3종 문서(전사본·정리본·결정사항) 목차 — 자동 생성")]
    lines.append(f"회의 **{len(found)}건**. 최근 순.\n")
    lines.append("| 날짜 | 주제 | 전사본 | 정리본 | 결정사항 |")
    lines.append("|---|---|---|---|---|")

    for (yymmdd, topic), docs in sorted(found.items(), reverse=True):
        try:
            d = datetime.strptime(yymmdd, "%y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            d = yymmdd
        cells = [f"[[{docs[k]}\\|✔]]" if k in docs else "—"
                 for k in ("전사본", "정리본", "결정사항")]
        lines.append(f"| {d} | {topic} | {cells[0]} | {cells[1]} | {cells[2]} |")

    missing = [(y, t, k) for (y, t), d in found.items()
               for k, _ in [(x, 0) for x in ("전사본", "정리본", "결정사항")] if k not in d]
    if missing:
        lines.append("\n## 빠진 문서\n")
        lines.append("3종이 다 갖춰지지 않은 회의다. 원본이 없어서일 수도 있고, ingest 가 덜 돈 것일 수도 있다.\n")
        for y, t, k in sorted(missing, reverse=True):
            lines.append(f"- `{y}-{t}` — **{k}** 없음")

    return "\n".join(lines) + "\n"


def build_layers():
    """층별 문서 목록 — vault 전체의 지도."""
    layers = [
        ("raw", "원본. 손대지 않는다", "vault/raw"),
        ("wiki", "정리된 지식. 에이전트가 갱신한다", "vault/wiki"),
        ("schema", "분류 체계와 운영 규칙. 사람만 고친다", "vault/schema"),
        ("log", "이력", "vault/log"),
    ]
    lines = [header("문서 지도", "vault 전체 문서를 층·폴더별로 나열 — 자동 생성")]

    for name, desc, root in layers:
        base = os.path.join(VAULT_DIR, root)
        if not os.path.isdir(base):
            continue
        docs = defaultdict(list)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if not x.startswith(".")]
            for fn in sorted(filenames):
                if fn.endswith(".md"):
                    docs[os.path.relpath(dirpath, VAULT_DIR)].append(
                        (fn[:-3], os.path.join(dirpath, fn)))
        total = sum(len(v) for v in docs.values())
        lines.append(f"\n## `{name}/` — {desc}  ({total}건)\n")
        for folder in sorted(docs):
            lines.append(f"**`{folder}/`**\n")
            for n, path in docs[folder]:
                s = summary_of(path)
                lines.append(f"- [[{n}]]" + (f" — {s}" if s else ""))
            lines.append("")
    return "\n".join(lines) + "\n"


def main():
    os.makedirs(INDEX_DIR, exist_ok=True)
    for fname, content in [("회의.md", build_meetings()), ("문서지도.md", build_layers())]:
        path = os.path.join(INDEX_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  생성: vault/index/{fname}")


if __name__ == "__main__":
    main()
