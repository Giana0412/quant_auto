# 개인 자동화

**개인 전용 저장소다.** 2026-08-19 에 회사용 위키·자동화를 전부 걷어냈다
(회사 정본은 `oursymbol/oao-wiki` 로 옮겨졌다).

> 🔒 이 레포는 **비공개**다. 공개로 바꾸지 말 것 — `personal/` 은 gitignore 되지만
> 자동화 스크립트에 개인 메일 주소·경로·구독 목록이 들어 있다.

---

## 매일 도는 것

| 시각 (KST) | 잡 | 하는 일 | 알림 |
|---|---|---|---|
| 20:00 | `newsletter-archive` | Gmail(IMAP)에서 구독 뉴스레터 수집 → 일일 다이제스트 | — |
| 20:15 | `market-snapshot` | 지수·환율·금 + 뉴스 언급 종목 스냅샷 | — |
| 20:30 | `daily-conclusion` | 위 둘을 종합 → 오늘의 결론 2종 | 🟢 **텔레그램 그룹** |
| 20:45 | `health-check` | 위가 다 돌았는지 점검 | 🔵 **개인방** |
| 월 09:00 | `newsletter-weekly-report` | 주간 리포트 | — |

launchd plist 는 `~/Library/LaunchAgents/com.giana.*.plist`.

**알림을 나눈 이유**: 시장·뉴스는 팀과 공유할 값이 있지만, 자동화가 고장 났다는
점검 알림은 팀이 볼 이유가 없다.

---

## 손으로 돌리기

```bash
.automation/archive-newsletters.sh          # 수집 + 다이제스트
.automation/market-snapshot.sh              # 시장
.automation/daily-conclusion.sh             # 종합 + 발송
.automation/health-check.sh                 # 점검 + 발송
.automation/health-check.sh 260817 --dry-run   # 과거 날짜 점검, 발송 안 함

python3 .automation/check_prompts.py        # 프롬프트 문자열 끊김 검사
```

---

## 데이터는 어디 있나

```
personal/          ← 자체 git 을 가진 별도 저장소. 이 레포는 추적하지 않는다
├── 09-newsletters/{newneek,uppity,bloomberg}/   수집된 발행물
│   └── _digests/                                일일 요약
└── 10-market/
    ├── data/                                    시장 스냅샷
    └── _conclusions/                            오늘의 결론
```

---

## 설정 파일 (gitignore, 권한 600)

| 파일 | 내용 |
|---|---|
| `.automation/.gmail.env` | `GMAIL_USER` · `GMAIL_APP_PASSWORD` (앱 비밀번호 16자리) |
| `.automation/.telegram.env` | `TELEGRAM_BOT_TOKEN` · `TELEGRAM_CHAT_ID`(개인) · `TELEGRAM_GROUP_ID`(그룹) |

---

## 겪은 함정 — 다시 밟지 말 것

| | 무엇 | 대책 |
|---|---|---|
| 🔴 **큰따옴표** | `PROMPT="…"` 안에 `"` 를 쓰면 문자열이 끊기고 뒤가 명령으로 실행된다 (`exit 127`). **세 번 밟았다.** `bash -n` 은 못 잡는다 — 문법은 정상이라서 | `check_prompts.py` |
| 🔴 **`set -e` + `pipefail`** | `ls`·`grep` 은 결과가 0건이면 1을 반환해 스크립트를 죽인다. 슬랙 수집이 6일간 이걸로 죽어 있었다 | `{ … \|\| true; }` 로 감쌀 것 |
| 🔴 **조용한 실패** | launchd 는 스크립트가 실패해도 종료코드 0 으로 "성공"이라 보고한다 | `health-check` 가 **산출물**을 보고 **매일** 알린다 |
| 🔴 **되먹임** | 점검 스크립트가 자기가 남긴 `🔴` 를 다시 세서 숫자가 불어났다 | 자기 출력은 `문제:` 로 표기 |
| ⚠️ **묵은 시장 데이터** | 휴장일에 직전 거래일 숫자가 "오늘 전일비"처럼 보고됐다 | `age_days` 로 `⏸ N일 전` 표시 |
