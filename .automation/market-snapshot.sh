#!/bin/bash
# 시장봇: 대표 지수/환율/금 고정 세트 + 오늘 뉴스에 언급된 종목을 yfinance로 스냅샷.
# launchd가 매일 20:15 KST에 호출한다 (com.giana.market-snapshot.plist).
# 뉴스레터 일일 다이제스트(archive-newsletters.sh, 20:00) 이후에 돌도록 스케줄돼 있다.

set -euo pipefail

VAULT_DIR="/Users/gyuhyeongkim/orca/projects/obsidian_test"
CLAUDE_BIN="/Users/gyuhyeongkim/.local/bin/claude"
LOG_DIR="$VAULT_DIR/.automation/logs"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"
cd "$VAULT_DIR"

# 네트워크 대기·재시도 — 깨어난 직후 Wi-Fi 가 안 올라온 상태에서 죽는 것을 막는다.
# 대기 기록도 일별 로그에 남긴다 (건너뛴 이유가 어딘가엔 있어야 한다).
source "$VAULT_DIR/.automation/lib/net.sh"
if ! wait_for_network >> "$LOG_FILE" 2>&1; then
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') 네트워크 없음 — 이번 실행 건너뜀 ===" >> "$LOG_FILE"
  exit 0
fi


# 체인이 자정을 넘겨도 단계들이 같은 날짜를 쓰도록 CHAIN_DATE 를 우선한다
TODAY_KST="${CHAIN_DATE:-$(TZ=Asia/Seoul date +%y%m%d)}"
TODAY_ISO_KST=$(TZ=Asia/Seoul date -j -f %y%m%d "$TODAY_KST" +%Y-%m-%d)

PROMPT="오늘 날짜(KST): ${TODAY_ISO_KST} (YYMMDD: ${TODAY_KST})

용도: **블룸버그 터미널 매매대회 전략 세팅.** 대회는 전 세계 주식을 사고, 평가는
벤치마크 대비 상대수익률이다. 그래서 절대 시세가 아니라 **벤치마크를 이기는 쪽이
어디인가**를 본다. 숫자는 전부 스크립트가 계산하니 옮겨 적기만 한다.

작업:
1. personal/09-newsletters/_digests/${TODAY_KST}-일일요약.md 가 있으면 읽고, 거기 언급된
   **상장 기업**의 야후 파이낸스 티커를 뽑는다 (예: 메타→META, 삼성전자→005930.KS,
   소프트뱅크→9984.T). 비상장(SpaceX, OpenAI 등)이나 확실하지 않은 것은 넣지 않는다.
   다이제스트가 없으면 종목 없이 진행한다.
2. 다음을 Bash로 실행한다. 티커는 공백으로 구분해 뒤에 붙인다 (없으면 인자 없이):
   .automation/.venv/bin/python .automation/market_metrics.py <티커들...>
   출력 절: [레짐] [지역] [섹터] [스타일] [종목] [스크리닝] [브레드스] [실적발표] [스트레치] [상관]
   - 표의 RS 열은 상대강도 지속일이다. 승N일 = 벤치마크를 N일째 이기는 중.
     3개월 성적이 좋아도 RS 가 '패'로 돌아섰으면 추세가 꺾인 것이므로 그 사실을 적는다
   - [스크리닝] 은 섹터·스타일 ETF 보유종목에서 만든 유니버스를 벤치마크 대비로 줄 세운 것이다.
     대회는 종목을 사므로 여기가 실제 매수 후보다
   - [브레드스] 는 몇 %가 벤치를 이기는지다. 낮으면 좁은 장(종목선택이 크게 먹힘)
   **이 숫자를 그대로 옮겨 적는다. 직접 계산하거나 추정하지 않는다.**
3. personal/10-market/data/${TODAY_KST}-시장데이터.md 를 작성한다:
   ---
   date: ${TODAY_ISO_KST}
   ---

   # ${TODAY_KST} 마켓

   ## 레짐
   (스크립트 [레짐] 절 그대로 + 한 줄 해석)

   ## 벤치마크 대비 초과수익
   ### 지역 / ### 섹터 / ### 스타일
   각각 표로: | 이름 | 1개월 | 3개월 | z | 베타 | 추세 |
   숫자는 스크립트 출력 그대로.

   ## 종목 후보
   ([스크리닝] 상위/하위를 표로: | 티커 | 1개월 | z | 베타 | 소속 |
    **하위 중 베타가 큰 것은 위험만 지고 지는 조합**이라 따로 짚는다.
    같은 섹터인데 상위·하위가 갈리면 그 사실이 제일 중요하다 —
    섹터 전체를 피할 게 아니라 그 안에서 갈라야 한다는 뜻이므로)

   ## 뉴스 연계 종목
   ([종목] 절이 있으면 같은 형식 표 + 왜 오늘 뉴스와 연결되는지 한 줄.
    없으면 '오늘 다이제스트에서 뽑을 상장 종목 없음')

   ## 장의 성격
   ([브레드스] 그대로 + [실적발표 14일 내] 가 있으면 그 목록.
    발표가 임박한 종목은 추세추종이 아니라 이벤트 베팅이 된다고 적는다)

   ## 주의
   - [스트레치] 절: |z| 큰 것 = 벤치마크 대비 과열/과매도. 평균회귀 후보
   - [상관] 절에서 0.8 이상인 쌍: **둘 다 사면 분산이 아니라 같은 베팅**이다.
     대회에 포지션당 20% 상한이 있어도 상관이 높으면 실질 집중이 된다는 뜻이라 꼭 적는다
   - 베타가 큰데 초과수익이 마이너스인 항목: 위험만 지고 못 이기는 조합이라 짚는다

4. 마지막에 한 줄 요약: 지금 벤치마크를 이기는 쪽 / 지는 쪽.

해석은 붙이되 **없는 숫자를 만들지 않는다.** 스크립트가 못 준 값은 없다고 적는다.

personal/10-market/data/ 외의 다른 파일은 건드리지 않는다. git commit/push는 하지 않는다."

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [시장봇] 실행 시작 ==="
  retry 3 60 "$CLAUDE_BIN" -p "$PROMPT" --allowedTools "Read Write Glob Grep Bash(.automation/.venv/bin/python .automation/market_metrics.py:*)" 2>&1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') [시장봇] 실행 종료 ==="
  echo
} >> "$LOG_FILE"
