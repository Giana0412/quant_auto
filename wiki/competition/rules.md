# 대회 규정

출처: Bloomberg *Trading Challenge Info* PDF + 공식 Terms & Conditions
🔴 **내가 본 PDF 는 2021년판이다.** 규칙 자체는 안정적이나 **날짜는 그해 것**이라 2026년 일정은 별도 확인이 필요하다.

## 매매 제약 — ✅확정
| 항목 | 내용 |
|---|---|
| 자본 | 가상 **$1,000,000** |
| 대상 | WLS 지수 내 **개별 종목만 — ETF 금지** |
| 방향 | **롱 온리** (공매도 불가) |
| 레버리지 | **금지** |
| 포지션 | 종목당 명목의 **20% 초과 불가** |
| 평가 | **WLS 지수 대비 상대 P&L** 최고 팀 우승 |

> 🔴 **레버리지 금지 때문에 실제 버그를 잡았다.** 역변동성 배분의 목표합이 `cap × 종목수`라
> `BOOK_N=6` 에서 120% 가 되어 **비중 합계 108% · 미배분 −8%** 가 나왔다 — 현금을 마이너스로
> 들고 레버리지를 쓰는 셈이다. [2026-09-13 실측 → `min(1.0, cap×n)` 로 수정]

## 팀 — ✅확정
- 학생 **3~5명** + 지도교수 1명 · LC Ghosts 는 3명(이정민 캡틴 · 김규형 · 이유찬)
- 팀 캡틴이 터미널 로그인 보유, **매매 입력은 캡틴 계정으로만**
- 참가 자격: **풀타임 학생 + 학교 소재 국가 거주**

## 지도교수 요건 — ✅확정 (T&C 원문)
> "Throughout the Registration Period **and the Challenge Period**, each Faculty Advisor must:
> be a faculty member in good standing at a School; **and** reside … **in the country in which
> their School is located**"

> "the faculty advisor will act as the students' advisor only but **not actively enter trades**"
> "A single faculty advisor may represent **multiple teams**"

**이 조항으로 후보 한 명이 탈락했다** — 교수 B는 이번 학기 NYU 체류라 거주 요건 미충족.
→ [advice/lee-dongwon.md](../advice/lee-dongwon.md)

**결과**: 교수 A(HKUST Finance) 승낙 · 등록 완료 [2026-09-17 / 09-20 확인]

## 학교 조건 — ⚠️미확인 영향
> "ELP Schools (**3+ billable terminals**) — unlimited teams.
> Non-ELP schools (**1 or 2 terminals**) may register **a single team**."

**HKUST 터미널은 2대** [3차 미팅 회의록]. 즉 **학교당 팀 하나만** 등록 가능하다.
우리는 등록을 마쳤으므로 문제없을 가능성이 높지만 확정은 아니다.

## 🔴 미확인 — 전략의 생사가 걸림
체결 방식이 **오버나이트 전략과 중소형 집중 전략의 성립 여부**를 결정한다.
→ [strategy/open-questions.md](../strategy/open-questions.md)
