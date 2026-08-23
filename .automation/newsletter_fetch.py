#!/usr/bin/env python3
"""Gmail 에서 뉴스레터를 IMAP 으로 받아 personal/09-newsletters/ 에 마크다운으로 저장한다.

기존에는 headless Claude 가 mcp__claude_ai_Gmail__* 커넥터로 가져왔다. 그런데
claude.ai 커넥터는 대화형 인증에 묶여 있어 **launchd 헤드리스 실행에서는 붙지 않았고**,
2026-08-10 실행이 통째로 실패했다(→ 다이제스트 없음 → 분석봇 '종합할 자료 없음' 연쇄).

메일을 가져오는 일은 기계적이라 에이전트가 낄 이유가 없다. slack_collect.py 와 같은
방침으로 순수 코드로 옮긴다:
  - 파이썬 표준 라이브러리만 쓴다 (node·npx·MCP 서버 불필요)
  - 앱 비밀번호는 만료되지 않는다 (OAuth 토큰 갱신 실패 걱정 없음)
  - 특정 LLM 에 묶이지 않는다 (260811 싱크 핵심논의 2)
요약·번역은 여전히 에이전트 몫이다 — 그건 실제로 판단이 필요한 일이라서다.

상태 이어받기: Gmail IMAP 확장 X-GM-THRID 로 스레드 ID 를 얻어 16진수로 바꾸면
Gmail API 가 주던 threadId 와 같은 값이 된다. 그래서 기존 _state.json 을 그대로 쓴다.

사용법:
  python3 .automation/newsletter_fetch.py [--dry-run] [--days 30]
"""

import argparse
import email
import email.utils
import imaplib
import json
import os
import re
import sys
from collections import defaultdict
from email.header import decode_header, make_header
from html.parser import HTMLParser

VAULT_DIR = os.environ.get(
    "VAULT_DIR", "/Users/gyuhyeongkim/orca/projects/obsidian_test"
)
ENV_FILE = os.path.join(VAULT_DIR, ".automation/.gmail.env")
BASE = os.path.join(VAULT_DIR, "personal/09-newsletters")
STATE_FILE = os.path.join(BASE, "_state.json")

# 발신자 : 저장 폴더. 새 뉴스레터를 추가하면 여기와 _README.md 둘 다 갱신한다.
SENDERS = {
    "whatsup@newneek.co": "newneek",
    "moneyletter@uppity.co.kr": "uppity",
    "noreply@news.bloomberg.com": "bloomberg",
}

# 실제 발행물이 아닌 메일 — 저장하지 않는다. 다만 상태에는 기록해서 매번 다시 보지 않게 한다.
NOT_AN_ISSUE = re.compile(
    r"구독\s*(확인|완료|신청)|환영합니다|welcome|you'?ve subscribed|"
    r"활용법|이용\s*안내|verify your email",
    re.I,
)


def die(msg):
    print(f"🔴 {msg}", file=sys.stderr)
    sys.exit(1)


def load_env():
    if not os.path.exists(ENV_FILE):
        die(
            f"Gmail 자격증명 파일이 없다: {ENV_FILE}\n"
            "   GMAIL_USER=<주소> / GMAIL_APP_PASSWORD=<앱 비밀번호 16자리> 형식으로 만들고 chmod 600 할 것"
        )
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("GMAIL_USER", "GMAIL_APP_PASSWORD"):
        if not env.get(k):
            die(f"{ENV_FILE} 에 {k} 가 없다")
    # 앱 비밀번호는 표시상 4자씩 띄어 주는데, 공백이 있으면 로그인이 실패한다
    env["GMAIL_APP_PASSWORD"] = env["GMAIL_APP_PASSWORD"].replace(" ", "")
    return env


class _Text(HTMLParser):
    """HTML 본문에서 읽을 수 있는 텍스트만 뽑는다. 문단 구조는 살린다."""

    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table", "section"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())

    def text(self):
        out = " ".join(self.parts)
        out = re.sub(r"[ \t]+", " ", out)
        out = re.sub(r"\s*\n\s*", "\n", out)
        return re.sub(r"\n{3,}", "\n\n", out).strip()


def body_of(msg):
    """text/plain 을 우선 쓰고, 없으면 text/html 을 텍스트로 바꾼다."""
    plain, html = None, None
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_filename():
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        raw = part.get_payload(decode=True)
        if not raw:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = raw.decode(charset, errors="replace")
        except LookupError:
            text = raw.decode("utf-8", errors="replace")
        if ctype == "text/plain" and plain is None:
            plain = text
        elif ctype == "text/html" and html is None:
            html = text

    if plain and plain.strip():
        body = plain
    elif html:
        p = _Text()
        p.feed(html)
        body = p.text()
    else:
        return ""

    # 광고 트래킹 링크는 본문 이해에 방해만 된다 — 마크다운 링크의 URL 부분만 지운다
    body = re.sub(r"https?://\S*?(list-manage|mailchimp|stibee|sendgrid|track)\S*", "", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def decode(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def safe_name(s, limit=60):
    s = re.sub(r'[/\\:*?"<>|\n\r\t]+', "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:limit].rstrip(" .") or "제목없음"


def fetch(args):
    env = load_env()
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
    known = len(state)

    query = " OR ".join(f"from:{s}" for s in SENDERS)
    query = f"({query}) newer_than:{args.days}d"

    # 🔴 timeout 을 반드시 준다. imaplib 은 기본값이 무한 대기라서, 연결이 멎으면
    # 스크립트가 영영 안 끝난다. 2026-08-22 20:10 에 시작한 실행이 **23시간** 동안
    # 여기 매달려 있었고, 그게 저녁 체인의 락을 붙잡아 그 뒤 사흘간 텔레그램이
    # 한 통도 안 나갔다. 멈추는 것보다 실패하는 게 낫다 — 실패는 건강검진이 잡는다.
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=60)
    try:
        try:
            M.login(env["GMAIL_USER"], env["GMAIL_APP_PASSWORD"])
        except imaplib.IMAP4.error as e:
            die(f"Gmail 로그인 실패: {e}\n"
                "   2단계 인증이 켜져 있고 앱 비밀번호가 맞는지 확인할 것")

        # 보관처리된 메일도 봐야 하므로 받은편지함이 아니라 전체보관함을 연다.
        # 전체보관함의 이름은 계정 언어에 따라 다르므로(\"[Gmail]/All Mail\", \"[Gmail]/전체보관함\" …)
        # 이름을 추측하지 않고 IMAP 이 알려주는 \All 속성으로 찾는다.
        if M.select('"[Gmail]/All Mail"', readonly=True)[0] != "OK":
            box = None
            for line in M.list()[1] or []:
                if rb"\All" in line:
                    box = line.decode(errors="replace").split(' "/" ')[-1].strip()
                    break
            if not box or M.select(box, readonly=True)[0] != "OK":
                die("전체보관함(All Mail)을 열지 못했다 — Gmail 설정에서 IMAP 이 켜져 있는지 확인할 것")

        status, data = M.search(None, "X-GM-RAW", f'"{query}"')
        if status != "OK":
            die(f"검색 실패: {status}")
        uids = data[0].split()
        print(f"최근 {args.days}일 안에서 {len(uids)}통 검색됨 (이미 처리 {known}건)")

        saved = defaultdict(int)
        skipped_known = skipped_notissue = 0

        for uid in uids:
            status, d = M.fetch(uid, "(X-GM-THRID RFC822)")
            if status != "OK" or not d or not isinstance(d[0], tuple):
                continue
            m = re.search(rb"X-GM-THRID (\d+)", d[0][0])
            if not m:
                continue
            thrid = format(int(m.group(1)), "x")   # Gmail API 의 threadId 와 같은 표기
            if thrid in state:
                skipped_known += 1
                continue

            msg = email.message_from_bytes(d[0][1])
            subject = decode(msg.get("Subject"))
            sender = decode(msg.get("From"))
            addr = email.utils.parseaddr(msg.get("From"))[1].lower()
            folder = next((v for k, v in SENDERS.items() if k in addr), None)
            if not folder:
                continue

            state[thrid] = True   # 저장하든 건너뛰든 다시 보지 않는다

            if NOT_AN_ISSUE.search(subject or ""):
                skipped_notissue += 1
                print(f"  건너뜀(발행물 아님): {subject[:50]}")
                continue

            dt = email.utils.parsedate_to_datetime(msg.get("Date"))
            fname = f"{dt:%y%m%d}-{safe_name(subject)}.md"
            path = os.path.join(BASE, folder, fname)

            doc = (
                "---\n"
                f"date: {dt:%Y-%m-%d}\n"
                f"sender: {sender}\n"
                f"subject: {subject}\n"
                f"gmail_thread_id: {thrid}\n"
                "---\n\n"
                f"# {subject}\n\n"
                f"{body_of(msg)}\n"
            )

            if args.dry_run:
                print(f"  [dry-run] {folder}/{fname}  ({len(doc)}자)")
            else:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(doc)
            saved[folder] += 1
    finally:
        try:
            M.logout()
        except Exception:
            pass

    if not args.dry_run:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.write("\n")

    total = sum(saved.values())
    if total:
        detail = ", ".join(f"{k} {v}건" for k, v in sorted(saved.items()))
        print(f"신규 {total}건 저장 ({detail})")
    else:
        print("신규 뉴스레터 없음")
    if skipped_known or skipped_notissue:
        print(f"  (이미 처리 {skipped_known}건, 발행물 아님 {skipped_notissue}건 건너뜀)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="파일도 상태도 쓰지 않고 결과만 출력")
    ap.add_argument("--days", type=int, default=30, help="며칠 전까지 검색할지 (기본 30)")
    fetch(ap.parse_args())
