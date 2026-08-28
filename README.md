# 개인 자동화

**개인 전용 저장소다.** 2026-08-19 에 회사용 위키·자동화를 전부 걷어냈다
(회사 정본은 `oursymbol/oao-wiki` 로 옮겨졌다).

> 🔒 이 레포는 **비공개**다. 공개로 바꾸지 말 것 — `personal/` 은 gitignore 되지만
> 자동화 스크립트에 개인 메일 주소·경로·구독 목록이 들어 있다.

---

## 매일 도는 것

**launchd 잡은 하나뿐이다** — `evening-chain`(이름은 옛날 그대로지만 실제론 아침 체인)이
06:00 에 떠서 네 단계를 순서대로 돌린다. 한국장 개장(09:00) 전에 텔레그램 그룹에
브리핑이 도착하게 하는 시각이다.

| 순서 | 단계 | 하는 일 | 알림 |
|---|---|---|---|
| ① | `archive-newsletters` | Gmail(IMAP)에서 구독 뉴스레터 수집 → 일일 다이제스트 | — |
| ② | `market-snapshot` | `market_metrics.py`(gs-quant) 로 지수·로테이션·스크리닝·모멘텀·빌드업·백테스트 스냅샷 | — |
| ③ | `daily-conclusion` | 위 둘을 종합 → 오늘의 결론 2종 | 🟢 **텔레그램 그룹** |
| ④ | `health-check` | 위가 다 돌았는지 점검 | 🔵 **개인방** |

| 시각 (KST) | 잡 |
|---|---|
| 매일 06:00 (+07:30 백업) | `evening-chain` |
| 월 06:30 | `strategy-backtest-weekly` — 로테이션 규칙의 과거 성적을 캐시에 갱신 |
| 월 09:00 | `newsletter-weekly-report` |

launchd plist 는 `~/Library/LaunchAgents/com.giana.*.plist`. 저장소에는 템플릿만
있고(`.automation/launchd/`), 설치는 손으로 `cp` + `launchctl load` 한다.

### 시장 지표는 gs-quant 로 계산한다

`market_metrics.py`(매일)·`strategy_backtest.py`(주간)는 [gs-quant](https://github.com/goldmansachs/gs-quant)의
`gs_quant.timeseries`(beta·correlation·RSI·MACD·zscore·max_drawdown)를 쓴다.
**Marquee API(기관 전용 실시간 데이터·Axioma/Barra 리스크모델)는 안 쓴다** — 개인은
발급받을 수 없어서다. 가격은 전부 yfinance 로 받고, gs-quant 는 그 위에서 순수
계산기로만 쓴다 (Marquee 인증 없이 오프라인으로 돈다).

- **`market_metrics.py`** — 지역·섹터·스타일 로테이션, 종목 스크리닝, 5종목 모델 북
  (상관필터 + 20% 상한), RSI·MACD 모멘텀, **빌드업**(오늘 레짐을
  `personal/10-market/_buildup/regime-log.jsonl` 에 append → "며칠째 유지" 계산),
  **백테스트 캐시 인용**(아래).
  - **위험조정 랭킹·사이징** — 정렬 기준이 raw 1개월 초과수익이 아니라
    `info_score`(변동성 대비 초과수익, 개별 종목판 정보비율에 가깝다)다. 모델 북
    비중도 flat 20%가 아니라 **역변동성 가중**(20% 상한은 유지) — 변동성 낮은
    종목에 더, 높은 종목에 덜 담는다. 변동성이 커서 한 달 반짝 튄 종목이 그냥
    상위로 올라오던 걸 막는다.
  - **청산 규칙** — `log_trade.py` 로 남긴 포지션에 트레일링손절(고점 대비
    -10%)·손절(진입가 대비 -7%)·익절 후보(수익 중 RSI 과열) 플래그를 붙인다.
    매도 지시가 아니라 후보 통지 — 지금까지 진입 신호만 있고 청산 신호가
    없던 공백을 메운다.
  - **전략모드** — 브레드스(스크리닝 종목 중 벤치 상회 비율)를 근거로 "오늘은
    로테이션 위주냐 스크리닝 위주냐"를 명시적으로 권고한다(좁은 장 <40%→
    스크리닝, 넓은 장 >60%→로테이션).
- **`strategy_backtest.py`** — "매달 벤치 대비 1개월 초과수익 상위를 상관필터로
  5개 골라 다음 달 보유" 라는 모델 북 방법론을, 개별종목이 아니라 지역·섹터·스타일
  ETF(13종, 생존편향 없음)로 walk-forward 재현한다. 리밸런스마다 **그 시점까지의
  데이터만** 써서 순위를 매기고 다음 구간 실현수익으로 평가한다(look-ahead 없음).
  결과를 `personal/10-market/_backtest/latest.json` 에 캐시 — 매일 재계산하기엔
  무겁고 결과도 하루 단위로 안 바뀌어서 주간(`strategy-backtest-weekly.sh`)으로 갱신하고
  `market_metrics.py` 가 읽어서 매일 브리핑에 한 줄로 인용한다(캐시가 10일 넘게
  오래되면 안 쓴다).
  ```bash
  .automation/.venv/bin/python .automation/strategy_backtest.py
  ```
- **`log_trade.py`** — 이 파이프라인은 블룸버그 터미널과 연동돼 있지 않다(개인
  참가자용 API 라이선스가 없어서 Marquee 를 못 쓰는 것과 같은 이유). 그래서
  실제 체결은 사람이 이 스크립트로 남겨야 한다:
  ```bash
  .automation/.venv/bin/python .automation/log_trade.py AAPL buy 230.50 \
      --shares 100 --note "RS10일, RSI과열 무시하고 진입"
  ```
  `market_metrics.py` 가 다음 실행부터 이 로그(`personal/10-market/_trades/
  trade-log.jsonl`)를 읽어 **[체결추적]** 절로 "진입가 대비 지금 얼마인지 ·
  벤치마크 대비 초과수익"을 매일 다시 계산해 브리핑에 붙인다 — 브리핑 신호
  자체(로테이션·스크리닝·모멘텀)와 실제 체결 결과를 나란히 봐야, 대회가 끝난
  뒤 "규칙이 틀렸나 실행이 틀렸나"를 가를 수 있다.

> 🔴 **왜 하나로 합쳤나** — 예전엔 잡 4개를 15분 간격으로 따로 걸었다.
> **노트북이 자고 있으면 그 전제가 무너진다.** macOS 는 잠든 사이 지나간
> `StartCalendarInterval` 잡을 **깨어날 때 한꺼번에** 실행하므로, 네 개가 같은 순간에
> 뜨고 순서가 사라진다. 2026-08-19 에 실제로 그래서 결론이 한 통도 안 갔다 —
> 분석봇이 재료가 준비되기 **전에** 돌아 "종합할 자료 없음" 하고 끝냈다.
> 잡을 하나로 줄이면 밀려도 순서는 지켜진다.

**알림을 나눈 이유**: 시장·뉴스는 팀과 공유할 값이 있지만, 자동화가 고장 났다는
점검 알림은 팀이 볼 이유가 없다.

---

## 손으로 돌리기

```bash
.automation/evening-chain.sh                # 네 단계 전부 (평소엔 이것만)

.automation/archive-newsletters.sh          # 수집 + 다이제스트
.automation/market-snapshot.sh              # 시장
.automation/daily-conclusion.sh             # 종합 + 발송
.automation/health-check.sh                 # 점검 + 발송
.automation/health-check.sh 260817 --dry-run   # 과거 날짜 점검, 발송 안 함

.automation/.venv/bin/python .automation/market_metrics.py         # 시장 지표만 (LLM 없이)
.automation/.venv/bin/python .automation/strategy_backtest.py      # 로테이션 규칙 백테스트 캐시 갱신
.automation/.venv/bin/python .automation/log_trade.py TICKER buy 123.45 --shares 10   # 실제 체결 기록

python3 .automation/check_prompts.py        # 프롬프트 문자열 끊김 검사
```

체인은 락(`logs/.evening-chain.lock`)으로 중복 실행을 막는다. 6시간 넘게 남은
락은 죽은 것으로 보고 회수한다.

### 오늘 하루만 건너뛰기

손으로 이미 돌려서 저녁에 또 나가는 걸 막고 싶을 때:

```bash
touch .automation/logs/.skip-$(TZ=Asia/Seoul date +%y%m%d)
```

표시 파일에 날짜가 박혀 있어 **다음 날 자동으로 무효**가 된다 — 껐다 켜는 걸
잊어버려서 며칠씩 안 도는 사고를 막기 위해서다.

---

## 데이터는 어디 있나

```
personal/          ← 자체 git 을 가진 별도 저장소. 이 레포는 추적하지 않는다
├── 09-newsletters/{newneek,uppity,bloomberg}/   수집된 발행물
│   └── _digests/                                일일 요약
└── 10-market/
    ├── data/                                    시장 스냅샷
    ├── _conclusions/                             오늘의 결론
    ├── _buildup/regime-log.jsonl                 [빌드업] append 로그 (하루 한 줄)
    ├── _backtest/latest.json                     [백테스트] 캐시 (주간 갱신)
    └── _trades/trade-log.jsonl                    실제 체결 기록 (log_trade.py, 사람이 남김)
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
