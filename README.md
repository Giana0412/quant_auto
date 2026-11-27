# quant_auto — 개인 시장 자동화

매일 아침 뉴스레터·시장 데이터를 모아 **오늘의 결론**을 써서 Slack `#quant-brief` 로 보내는 파이프라인과,
그 위에서 하는 ML·리스크 연구를 담은 개인 저장소다.

| 문서 | 무엇 |
|---|---|
| **이 README** | 무엇이 언제 돌고, 어떻게 손으로 돌리고, 어떻게 운영하나 |
| [`.automation/NOTES.md`](.automation/NOTES.md) | 스크립트마다 **왜 이렇게 만들었나** (설계 메모) |
| [`wiki/`](wiki/index.md) | 무엇을 알고 어떻게 알았나 — 대회 규정·자문·결정 로그·실측 결과 |
| Jira `KAN` | 할 일과 장애 기록 (아래 [작업 흐름](#작업-흐름)) |

> 🔒 **비공개 저장소다. 공개로 바꾸지 말 것** — `personal/` 은 gitignore 되지만
> 자동화 스크립트에 개인 메일 주소·경로·구독 목록이 들어 있다.
> 2026-08-19 에 회사용 위키·자동화는 전부 걷어냈다(회사 정본은 `oursymbol/oao-wiki`).

---

## 매일 도는 것

launchd 잡 `evening-chain`(이름은 옛날 그대로지만 아침 체인이다)이 **06:00** 에 떠서 아래 단계를
**순서대로** 돌린다. **07:30** 에 한 번 더 뜨는데, 그날 이미 브리핑이 나갔으면 바로 끝난다(백업).
시각은 모두 **맥 시계 기준**이다.

| 단계 | 하는 일 | 상한 | 나가는 곳 |
|---|---|---|---|
| `archive-newsletters` | Gmail(IMAP)에서 구독 뉴스레터 수집 → 일일 다이제스트 | 15분 | — |
| `market-snapshot` | `market_metrics.py`(yfinance + gs-quant 계산) → 지수·로테이션·스크리닝·모델 북·매크로일정 스냅샷 | 10분 | — |
| `agent-review` | 모델 북 종목에 TradingAgents 등급(세컨드 오피니언, 북은 안 바꾼다) | 33분 | — |
| `daily-conclusion` | 위를 종합해 **오늘의 결론** 2종(본편·쉬운 버전) 작성 | 8분 | 🟢 Slack `#quant-brief` (Sigma) |
| `dashboard-push` | 결론을 팀 대시보드(Streamlit) 브리핑 탭으로 — 구글 시트 경유 | 1분 | 구글 시트 |
| `event-alerts` | 감시 창에 새로 들어온 이벤트(FOMC·CPI 등)만 알림. 월요일엔 일정도 다시 긁는다 | 1.5분 | 🟡 Slack (조용한 날은 없음) |
| `health-check` | 위 산출물이 다 생겼는지 점검 | 2분 | 로그만 (`logs/YYYYMMDD.log`) |

`headline-collect`(헤드라인 ML 수집)는 꺼져 있다 — `evening-chain.sh` 의 STEPS 주석 참고.

### 그 밖의 잡

| 시각 | 잡 | 하는 일 |
|---|---|---|
| 매일 14:00 | `chain-watchdog` | 오늘 체인이 완주했나 확인. 문제면 🚨 Slack + **Jira 인시던트**, 정상이면 열린 인시던트를 닫는다 |
| 월·화 06:30 | `strategy-backtest-weekly` | 로테이션 규칙 백테스트 캐시 갱신 |
| 월 09:00 | `newsletter-weekly-report` | 주간 뉴스레터 리포트 |

plist 는 `~/Library/LaunchAgents/com.giana.*.plist`. 저장소에는 템플릿만 있고(`.automation/launchd/`),
설치는 손으로 `cp` + `launchctl load` 한다. 잡을 따로 두지 않고 체인 하나로 묶은 이유는
NOTES 의 "왜 하나로 합쳤나" — 노트북이 자다 깨면 밀린 잡이 한꺼번에 떠서 순서가 사라진다.

---

## 손으로 돌리기

```bash
.automation/evening-chain.sh                     # 체인 전부 (평소엔 이것만)

.automation/archive-newsletters.sh               # 단계 하나씩
.automation/market-snapshot.sh
.automation/daily-conclusion.sh                  # 종합 + Slack 발송
.automation/health-check.sh 260817 --dry-run     # 과거 날짜 점검
.automation/chain-watchdog.sh --dry-run --now    # 감시견: 보낼 내용만 보기

.automation/send_slack.sh <파일> [--alert]        # 아무 마크다운이나 #quant-brief 로

PY=.automation/.venv/bin/python
$PY .automation/market_metrics.py                # 시장 지표만 (LLM 없이)
$PY .automation/event_alerts.py --dry-run        # 이벤트 알림 미리보기
$PY .automation/econ_calendar.py [--merge]       # 경제지표 일정 긁기 (--merge 로 캘린더에 반영)
$PY .automation/log_trade.py AAPL buy 230.50 --shares 100 --sector 기술 --note "..."   # 실제 체결 기록

python3 .automation/check_prompts.py             # 프롬프트 문자열 끊김 검사
python3 .automation/wiki_lint.py                 # 위키 점검
```

체인은 락(`logs/.evening-chain.lock`, 안에 PID)으로 중복 실행을 막는다. 락을 쥔 프로세스가 죽었으면 회수한다.

**오늘 하루만 건너뛰기** — 손으로 이미 돌려서 또 나가는 걸 막고 싶을 때:

```bash
touch .automation/logs/.skip-$(TZ=Asia/Seoul date +%y%m%d)
```

날짜가 박혀 있어 다음 날 자동으로 무효가 된다. 감시견도 이 날은 고장으로 보지 않는다.

---

## 스크립트 지도

설계 근거는 전부 [`.automation/NOTES.md`](.automation/NOTES.md) 에 있다.

| 스크립트 | 체인 | 무엇 |
|---|---|---|
| `newsletter_fetch.py` · `archive-newsletters.sh` | ① | 뉴스레터 수집·다이제스트 |
| `market_metrics.py` · `market-snapshot.sh` | ② | 로테이션·스크리닝(중소형 위주 206종목)·모델 북(6종목, 섹터 상한, 역변동성)·청산 후보·빌드업·매크로일정 |
| `paper_track.py` | ② | 매일 북을 기록하고 스스로 채점 — 유일한 편향 없는 성적 |
| `lseg_reports.py` · `research_feeds.py` | ② | LSEG 주간 리포트·기관 리서치 링크 (robots.txt 준수) |
| `watchlist.py` | ② | 팀원 조사 종목 창구 (`add`/`drop`/`list`) |
| `agent_review.py` · `claude_cli_llm.py` | ③ | TradingAgents 세컨드 오피니언 — LLM 은 구독(`claude -p`) |
| `daily-conclusion.sh` | ④ | 오늘의 결론 작성·발송 |
| `push_briefing.py` · `dashboard-push.sh` | ⑤ | 팀 대시보드로 |
| `event_alerts.py` · `econ_calendar.py` · `calendar_export.py` | ⑥ | 이벤트 알림, 일정 수집(Fed·BEA·FXMacroData), `.ics` 내보내기 |
| `health-check.sh` · `chain-watchdog.sh` · `jira_incident.py` | ⑦ · 14:00 | 점검, 감시견, Jira 인시던트 |
| `strategy_backtest.py` | 주간 | 로테이션 walk-forward 백테스트 (🔴 숫자는 창 정렬 노이즈가 크다) |
| `momentum_screen.py` · `news_sentiment.py` | 손 | 공격형 스크리너, 뉴스 센티멘트 ↔ 가격 반응 |
| `log_trade.py` · `decision_log.py` | 손 | 실제 체결·결정 기록 |
| `send_slack.sh` | — | 모든 발송의 출구. `send_telegram.sh` 는 남겨만 둔 옛 경로 |
| `macro-calendar.json` | — | FOMC·CPI·고용 등 일정. 수동 입력분은 덮어쓰지 않는다(`auto_source` 로 구분) |

### 연구 (`ml/`)

| 폴더 | 무엇 |
|---|---|
| [`ml/research/`](ml/research/README.md) | 연구 하네스 — 누수 없는 패널, 시간순 CV, 비용 포함 평가, 실험 장부 |
| `ml/pead/` | 실적 발표 후 drift(PEAD) 검정과 스크리너 조건화 |
| [`ml/headline-sentiment/`](ml/headline-sentiment/README.md) | 헤드라인 감성 모델 — 78단어 사전을 트랜스포머로 이길 수 있나 |

---

## 운영

### 클론 두 개

| 클론 | 경로 | 용도 |
|---|---|---|
| 개발 | `~/orca/quant_auto` | 작업. 동시에 여러 작업이면 worktree |
| 운영 | `~/orca/projects/quant_auto` | launchd 가 여기서 돈다 (`VAULT_DIR`) |

배포 = PR 을 `main` 에 병합 → 운영 클론에서 `git pull --ff-only`.
운영 클론의 `macro-calendar.json` 은 수집 결과로 로컬 수정이 남아 있는 게 정상이다.

### 처음 설치할 것

```bash
brew install coreutils          # timeout — 없으면 체인이 시작하자마자 멈춘다
cd ~/orca/projects/quant_auto/.automation
uv venv --python 3.13 .venv-ta  # agent-review 용 TradingAgents
uv pip install --python .venv-ta/bin/python "tradingagents @ git+https://github.com/TauricResearch/TradingAgents@v0.7.1"
```

**절전 대책** — 배터리 + 뚜껑 닫힘이면 `caffeinate` 로는 못 막아 체인이 몇 시간씩 기어간다.
체인이 도는 동안만 `pmset disablesleep` 을 걸고 끝나면 푼다(그 두 명령만 sudo 비밀번호 없이):

```bash
# /etc/sudoers.d/quant-auto-pmset (0440 root:wheel)
<user> ALL=(root) NOPASSWD: /usr/bin/pmset -a disablesleep 1, /usr/bin/pmset -a disablesleep 0

sudo pmset repeat wakeorpoweron MTWRFSU 05:55:00   # 체인 5분 전 기상
```

### 비밀값

토큰은 키체인에, 나머지는 `.automation/` 의 env 파일(gitignore, 권한 600)에 둔다.

| 어디 | 이름 | 쓰는 곳 |
|---|---|---|
| 키체인 | `newsbot-slack-bot` | `send_slack.sh` — 개인 워크스페이스의 Talon 앱 봇 토큰. 봇이 `#quant-brief` 멤버여야 한다 |
| 키체인 | `quant-auto-jira` (계정 = Atlassian 이메일) | `jira_incident.py` — Atlassian API 토큰 |
| 파일 | `.gmail.env` | `GMAIL_USER` · `GMAIL_APP_PASSWORD` |
| 파일 | `.sheet.env` | `push_briefing.py` — 대시보드 시트 |
| 파일 | `.anthropic.env` (선택) | `TA_BACKEND=anthropic` 으로 agent-review 를 API 키로 돌릴 때만 |

키체인에 넣을 때 `!` 프롬프트에서 `-w` 로 비밀번호를 물으면 **빈 값이 저장된다**.
토큰을 복사한 뒤 `-w "$(pbpaste)"` 로 넣는다.

### 작업 흐름

Jira 프로젝트 `KAN` — 에픽 넷 아래에 티켓을 단다.

| 에픽 | 무엇 |
|---|---|
| KAN-13 | PEAD 연구 |
| KAN-14 | 헤드라인 ML |
| KAN-15 | risk-lab (VaR·ES·스트레스·기여도) |
| KAN-16 | 운영 자동화 — 감시견 인시던트가 여기 붙는다 |

티켓을 먼저 만들고 **브랜치 이름과 커밋에 키를 넣는다**(`fix/KAN-19-...`). 감시견 인시던트는
라벨 `watchdog` 으로 찾으므로, 손으로 만든 장애 티켓도 이 라벨을 달면 자동으로 닫힌다.

---

## 데이터는 어디 있나

```
personal/          ← 자체 git 을 가진 별도 저장소. 이 레포는 추적하지 않는다
├── 09-newsletters/{newneek,uppity,bloomberg}/   수집된 발행물
│   └── _digests/                                일일 요약
└── 10-market/
    ├── data/                                    시장 스냅샷
    ├── _conclusions/                            오늘의 결론
    ├── _agents/agent-log.jsonl                  TradingAgents 등급
    ├── _buildup/regime-log.jsonl                [빌드업] 하루 한 줄
    ├── _backtest/latest.json                    [백테스트] 캐시 (주간)
    └── _trades/trade-log.jsonl                  실제 체결 (log_trade.py)

.automation/logs/  YYYYMMDD.log (체인) · watchdog.log · .skip-YYMMDD
```

---

## 겪은 함정 — 다시 밟지 말 것

| | 무엇 | 대책 |
|---|---|---|
| 🔴 **절전** | 배터리 + 뚜껑 닫힘이면 체인이 DarkWake 때만 조금씩 전진한다. 절전 중엔 `timeout` 타이머도 멈춰서 상한이 무력하다. 2026-11-24~26 브리핑 3일 중단(KAN-19) | 예약 기상 + 체인 중 `disablesleep` ([운영](#처음-설치할-것)) |
| 🔴 **사라진 `timeout`** | 의존성으로 깔린 coreutils 가 brew 정리 때 같이 지워져 11/27 체인이 시작 직후 멈췄다 | `brew install coreutils` 로 **직접 설치**해 둔다 |
| 🔴 **깨어난 직후 네트워크** | 감시견이 절전에서 막 깬 순간에 돌면 DNS·타임아웃으로 Slack·Jira 가 실패한다 | 발송 전 최대 2분 대기, Jira 연결 실패는 재시도 |
| 🔴 **중복 발송 검사 문구** | 07:30 백업은 로그의 `발송 성공 → 그룹` 으로 "오늘 나갔나"를 판단한다. 다른 발송이 같은 문구를 찍으면 백업이 엉뚱하게 건너뛴다 | 알림은 `→ 알림` 으로 찍는다(`send_slack.sh --alert`) |
| 🔴 **큰따옴표** | `PROMPT="…"` 안의 `"` 가 문자열을 끊고 뒤가 명령으로 실행된다(`exit 127`). 세 번 밟았다. `bash -n` 은 못 잡는다 | `check_prompts.py` |
| 🔴 **`set -e` + `pipefail`** | `ls`·`grep` 이 0건이면 1을 반환해 스크립트를 죽인다 | `{ … \|\| true; }` |
| 🔴 **조용한 실패** | launchd 는 스크립트가 실패해도 "성공"이라 보고한다 | 건강검진은 **산출물**을 보고, 감시견은 **완주 표시**를 본다 |
| 🔴 **되먹임** | 점검 스크립트가 자기가 남긴 `🔴` 를 다시 세서 숫자가 불어났다 | 자기 출력은 `문제:` 로 표기 |
| ⚠️ **묵은 시장 데이터** | 휴장일에 직전 거래일 숫자가 "오늘 전일비"처럼 보였다 | `age_days` 로 `⏸ N일 전` 표시 |
| ⚠️ **방법론 변경 = 빌드업 단절** | 유니버스를 120→206 으로 넓힌 날 브레드스가 47.1%→41.4% 로 떨어졌다 — 시장이 아니라 분모가 바뀐 것 | 기준을 바꾼 날은 로그에 적고, 전후 추세를 이어 읽지 말 것 |
