# ml/research — ML 연구 하네스 (KAN-22)

S&P 500 횡단면·변동성·실적 연구가 같이 쓰는 재료와 잣대. 미래 정보가 안 새는 패널, 시간순 CV,
비용 포함 평가, 시도 횟수를 세는 실험 장부를 한 벌로 둔다. 계산 규칙(편입 이력, 베타조정 초과수익,
반응일 d0, 직전 90일 SUE 백분위, Newey–West)은 `ml/pead/pead.py`·`overlay.py` 를 import 해서 쓴다.

| 파일 | 내용 |
|---|---|
| `panel.py` | 원자료 읽기, 피처 행렬, 월말 패널, 일간(변동성) 패널, 실적 이벤트 표, 횡단면 전처리, 캐시 |
| `cv.py` | 확장창 walk-forward (퍼지·엠바고·시간순 검증), `predict_oos` |
| `evaluate.py` | OOS R², 순위 IC, 10분위 롱숏·상위 롱(0/10/25bp), 짝지은 비교, Diebold–Mariano |
| `registry.py` | 실험 장부(jsonl), Holm/BH, Deflated Sharpe Ratio |
| `baselines.py` | `Model` 인터페이스, `Zero` · `OLS` · `RidgeCV` · `LassoCV` |
| `test_research.py` | 미래 차단·퍼지·심은 신호·위약·DSR 점검 (19개) |

## 경로

| 환경변수 | 기본값 | 내용 |
|---|---|---|
| `QA_PEAD_RUNS` | `<저장소 본체>/ml/pead/runs` | 입력 캐시 `px.pkl`·`earnings.pkl`·`membership.pkl` (pead 가 받아 둔 것, 다운로드 안 함) |
| `QA_RESEARCH_RUNS` | `<저장소 본체>/ml/research/runs` | 출력 캐시 (parquet) + `ledger.jsonl` |

git worktree(`.claude/worktrees/…`) 안에서 돌아도 기본값은 **저장소 본체**를 가리킨다 — 워크트리마다
캐시를 다시 만들지 않는다. 둘 다 gitignore.

Python: `ml/headline-sentiment/.venv/bin/python` (pandas 3, sklearn, torch, lightgbm, pytest).

## 빠른 시작

```bash
cd ml
../headline-sentiment/.venv/bin/python -m research.panel          # 캐시 빌드 (~11초, 최대 메모리 ~0.8GB)
../headline-sentiment/.venv/bin/python -m pytest research/test_research.py -q
```

| 캐시 | 크기 | 빌드 |
|---|---|---|
| `monthly_2014-01-01.parquet` | 67,779행 · 월말 154개 (2014-01 ~ 2026-10) · 티커 586 · 월평균 440종목 · 라벨 있는 행 67,277 | 피처 행렬 7초 + 1초 |
| `events_2014-01-01.parquet` | 발표 28,875건 · 티커 598 · 2014-01 ~ 2026-11 | 0.4초 |
| `daily_2014-01-01_1-5-22.parquet` | 1,428,123행 · 세션 3,245 · 티커 588 · float32 117MB | 2초 |

캐시는 `px.pkl` 등 원자료가 더 새로우면 다시 만든다(`refresh=True` 로 강제).

```python
import sys; sys.path.insert(0, "<repo>/ml")
from research import panel, cv, evaluate, registry, baselines

P = panel.monthly_panel()                               # 캐시에서 읽는다
P = P.dropna(subset=["y_ex"]).reset_index(drop=True)    # 마지막 월말(라벨 없음)은 실전 예측용
Q, cols = panel.prepare(P)                              # 날짜별 순위 [-1,1] + 날짜별 중앙값 대체 + <col>_na

folds = cv.walk_forward(Q["date"], Q["label_end"], first_test="2018-01-01",
                        refit_months=12, val_months=24)  # 매년 재학습 · 매달 예측 · 마지막 24개월 검증
R = cv.predict_oos(Q, folds, cols, "y_ex", baselines.RidgeCV)   # date, ticker, y, pred, fold

s = evaluate.summarize(R, bench=evaluate.hist_mean(P, "y_ex", Q["date"]))
print(evaluate.table(s))
registry.log("kan-xx-gbm", "ridge-all", {"cols": cols, "refit": 12}, s)   # 평가마다 반드시

base = cv.predict_oos(Q, folds, cols, "y_ex", lambda: baselines.OLS(cols=[cols.index(c) for c in baselines.CLASSIC]))
print(evaluate.compare(R, base))                         # 짝지은 증분 NW t, DM

L = registry.load("kan-xx-gbm")
L = registry.deflate(registry.adjust(L, "ls_c10_p"), "ls_c10")   # Holm/BH, DSR (N = 장부 행 수)
```

## API

### panel
| 함수 | 반환 |
|---|---|
| `load_raw(data_dir=None, tickers=None, end=None) -> Raw` | `Raw.C`·`V`(세션×티커, SPY 포함), `E`(실적), `win`·`sector`(편입 이력) |
| `daily_features(raw, dtype="float32") -> dict[str, DataFrame]` | `FEATURES` 각각 세션×티커 행렬 |
| `monthly_panel(raw=None, start="2014-01-01", cache=True, refresh=False)` | 월말 패널 (아래) |
| `daily_panel(raw=None, start=..., horizons=(1,5,22), ...)` | 일간 변동성 패널 (아래) |
| `earnings_events(raw=None, start=..., ...)` | 발표 한 건 = 한 행 (아래) |
| `rank_normalize(P, cols, by="date")` | 날짜별 순위 → [-1,1] (동률 평균, NaN 유지) |
| `fill_missing(P, cols, by="date", indicators=True) -> (P, cols)` | 날짜별 중앙값 대체 + `<col>_na` |
| `prepare(P, cols=None) -> (P, cols)` | 위 둘을 차례로 |
| `beta_excess(C) -> (R, beta_now, ex)` | overlay.beta_excess 와 같은 초과수익 + 피처용 β |
| `member_mask(raw)`, `month_ends(sessions)`, `add_sectors(P, raw)`, `describe(P)` | |

`raw` 를 넘기면 캐시를 쓰지도 덮지도 않는다(부분 데이터 테스트가 캐시를 망치지 않게).

### cv
| 함수 | |
|---|---|
| `walk_forward(dates, label_end=None, *, first_test, refit_months=12, val_months=0, embargo_days=0, min_train_dates=24, last_test=None) -> list[Fold]` | `Fold.train`·`val`·`test`(위치 인덱스), `.fit`(=train+val), `test_start`, `test_end` |
| `predict_oos(P, folds, cols, label, make_model, date_col="date", keep=("ticker",), refit_on_val=False)` | 시험 행의 `date, ticker, y, pred, fold` |

퍼지 규칙: 학습 행은 `date < t_test` 그리고 `label_end ≤ t_test − embargo`. 검증 경계에서도 같은 규칙으로
안쪽 학습을 한 번 더 퍼지한다. `label_end == t_test` 인 행(시험 직전 월말)은 그 날 종가에 라벨이 확정되므로 남는다.
이벤트 표처럼 기준일이 `date` 가 아니면 `walk_forward(E["d0"], E["d0_next"], ...)` 식으로 열을 골라 넘긴다.

### evaluate
| 함수 | |
|---|---|
| `summarize(R, ppy=12, costs=(0,10,25), n_q=10, bench=None) -> dict` | `r2_zero, r2_hist, ic_{mean,std,ir,t,p,hit,n}, {ls,top}_c{c}_{ann,vol,sr,t,p,srpp,skew,kurt,n}, topuni_c0_*, turnover_{ls,top}` |
| `compare(Ra, Rb, ppy=12, loss="mse"|"qlike") -> dict` | `ic_diff_*, {ls,top}_c{c}_diff_{ann,t,p}, dm_stat, dm_p` (같은 (date,ticker) 만) |
| `rank_ic(R)`, `ic_summary(ic)`, `portfolios(R, n_q=10)`, `oos_r2(y, pred, bench=None)`, `hist_mean(P, label, dates)` | |
| `diebold_mariano(loss_a, loss_b, h=1)`, `loss_mse`, `loss_qlike(rv, f)` (분산 단위), `nw_t`, `series_stats(x, ppy)`, `table(s)` | |

변동성 연구에서는 `ppy=252` 로, 예측 비교는 `compare(..., loss="qlike")` 또는 `diebold_mariano` 를 직접 쓴다
(날짜별 평균 손실을 먼저 만들고 그 시계열로 검정한다).

### registry
`log(study, name, params, metrics, notes=None)`, `load(study=None)`, `n_trials(study)`, `holm(p)`, `bh(p)`,
`adjust(L, p_col)`, `expected_max_sr(N, var)`, `psr(sr, sr_bench, T, skew, kurt)`,
`deflated_sharpe(sr, T, N, sr_var=None, skew=0, kurt=3)`, `deflate(L, prefix="ls_c10")`.
SR 은 전부 **기간 단위**(월간이면 월 SR) — `summarize` 의 `*_srpp`.

### baselines
`Model` = `fit(X_train, y_train, X_val=None, y_val=None) -> self` · `predict(X)` (선택: `refit(X, y)`).
`Zero`, `OLS(cols=None)`, `RidgeCV(alphas=None)`, `LassoCV(alphas=None)`, `CLASSIC = ["mom_12_1", "dvol_1m", "mom_1m"]`.
LightGBM·MLP·LSTM 은 연구 코드에서 같은 인터페이스로 구현한다(예시는 `baselines.py` docstring).

## 패널 정의

**월말 패널** — 한 행 = (월말 세션 t, 그날 S&P 500 편입 중이고 t 종가가 있는 종목). SPY 제외.
데이터 마지막 달(끝나지 않은 달)은 월말이 아니라서 행이 없다. 가장 마지막 월말 행은 라벨이 NaN.

| 열 | 정의 |
|---|---|
| `y_ex` | t+1 … t'(다음 월말) 세션의 베타조정 초과수익 합. 초과 = r − clip(β₂₅₀ shift 1, 0, 3)·r_SPY |
| `y_raw` | C[t']/C[t] − 1 (t' 가격이 없으면 창 안 마지막 가격) |
| `spy_fwd` | 같은 창 SPY 수익 |
| `fwd_days` | 창 안 수익이 있는 세션 수 (상폐면 작다) |
| `label_end` | t' — 퍼지에 쓴다 |

**피처** (전부 t 종가까지, `panel.FEATURES` 와 같다)

| 이름 | 정의 |
|---|---|
| `mom_1m` | C[t]/C[t−21] − 1 (단기 반전, 기대 부호 −) |
| `strev_1w` | C[t]/C[t−5] − 1 |
| `exret_1m` | 최근 21세션 베타조정 초과수익 합 |
| `mom_3m` | C[t−21]/C[t−63] − 1 |
| `mom_6m` | C[t−21]/C[t−126] − 1 |
| `mom_12_1` | C[t−21]/C[t−252] − 1 |
| `maxret_1m` | 최근 21세션 일간수익 최대 (최소 15) |
| `rvol_1m` · `rvol_3m` | 최근 21(최소 15) · 63(최소 40)세션 일간수익 표준편차 × √252 |
| `ivol_3m` | 최근 63세션 베타조정 초과수익 표준편차 × √252 |
| `beta` | t 까지 250세션(최소 120) cov(r, r_SPY)/var(r_SPY) — 클립 없음 |
| `beta_down` | 같은 창에서 r_SPY<0 인 날만 (최소 50쌍) |
| `vol_chg` | log(21세션 평균 거래량 / 252세션 평균 거래량) |
| `dvol_1m` | log(21세션 평균 C×V) — **시가총액 대용** (시총 이력 없음) |
| `high52` | C[t] / 252세션 최고 종가 (최소 120) |
| `sue_raw` | 가장 최근 발표(반응일 d0 ≤ t)의 (실제 − 예상 EPS) ÷ 발표 전날 종가, 클리핑 없음 |
| `sue_pct` | 그 SUE 가 직전 90일(달력, 같은 날 제외) 편입 종목 발표 중 몇 %보다 큰가 (100건 미만 NaN) |
| `sue_persist` | 최근 8건 SUE 의 1차 자기 순위상관 (쌍 7개, 최소 6건) |
| `days_since_ann` | t − 최근 d0 (달력일) |
| `ea_month` | d0 ∈ (t−30일, t] 발표가 있으면 1 |
| `ea_next_exp` | d0 ∈ (t−91일, t−61일] 발표가 있으면 1 (분기 주기상 다음 달 발표 예상) |

반응일 d0: 발표 시각 09:30 ET 전이면 그날 세션, 이후면 다음 세션, 시각 00:00 행은 제외 (pead 규칙).
업종은 기본 피처가 아니다 — `add_sectors` 의 🔴 경고 참고(오늘의 GICS, 편출 종목은 업종 없음 = 미래 정보).

**일간 패널** (변동성) — 한 행 = (세션, 편입 종목), float32. `r, ex, abs_r, rv_5, rv_22, rv_66`
(√ 최근 n세션 r² 평균), `beta`, `mkt_r, mkt_rv_5, mkt_rv_22` (SPY), 라벨 `rv_fwd_{1,5,22}` = √(t+1…t+h r² 평균)
과 `label_end_{h}`. QLIKE 는 분산 단위이므로 `rv_fwd_h ** 2` 로 넣는다.

**실적 이벤트 표** — 발표 한 건 = 한 행 (편입 여부 무관, `member` 열로 구분). `sue`, `sue_pct`, `persist`,
`pre_<피처>`(발표 시각 전에 끝난 마지막 세션 `date_pre` 종가 기준, `pre_sue_*` 는 직전 발표), `intraday`(장중 발표 —
`date_pre` 가 d0 두 세션 전; 이 행의 `sue` 분모·`ear` 는 pead 정의라 당일 반응이 섞인다, ~1%), 라벨 `ear`(d0 하루 초과),
`drift20`·`drift60`(d0+2 … d0+h, pead 와 같은 d0+1 종가 진입), `sue_next`·`d0_next`(200일 안 다음 발표),
`label_end_drift{h}`. 기준일 고르는 법은 `earnings_events` docstring.

## 점검 결과 (2026-11-26)

- `pytest research/test_research.py` — 19 passed.
- 미래 차단: 2021-06-15 뒤 가격·거래량·실적(반응일이 그 뒤인 발표)을 바꾸거나 잘라 내도 그때까지의 21개 피처와
  확정된 라벨이 비트 단위로 같다. 이 점검에서 "발표 이력이 아직 없는 종목"의 발표 플래그가 NaN/0 으로 갈려
  미래 발표 존재가 새던 것을 찾아 고쳤다. 별도 리뷰에서 장중 발표의 `date_pre` 가 발표 당일(반응 포함)이던 것을 찾아 고쳤다.
- 심은 신호(합성, 라벨과 상관 0.1): IC +0.105 (NW t +18.3), 롱숏 10bp 연 +35%, 잡음 기준 대비 증분 t +11.5, DM −10.5.
- 심은 신호(실데이터, `y_ex` + 잡음 10σ 를 Ridge 피처로 추가): IC +0.082 (t +7.1), 롱숏 10bp 샤프 2.0,
  Ridge 대비 증분 연 +22.8% (t +5.3), DSR 0.999. 신호 없는 OLS-3·Ridge·Lasso 는 IC t < 1, DSR < 0.02.
- 위약(날짜 안에서 섞은 라벨 10회): IC t 평균 +0.12, |t|>2 0회.
- DSR: 무작위 전략 50개 최대 SR 몬테카를로 0.1433 vs 공식 SR0 0.1440.

## 알려진 한계

- **시가총액·재무 이력(point-in-time)이 없다.** 크기는 거래대금(`dvol_1m`)으로 대신한다. 수정종가 × 거래량이라
  과거 거래대금이 배당 조정만큼 약간 작다. 장부가/시가 같은 가치 피처는 없다.
- **생존 편향이 남아 있다.** 2013 이후 편출 종목 249개 중 yfinance 에 가격이 남은 건 101개뿐 — 월평균 종목 수가
  2014년 371 → 2026년 493 으로, 초기 연도일수록 '살아남은 종목' 쪽으로 기운다.
- **상장폐지 수익이 없다.** 창 중간에 가격이 끊기면 그 뒤 초과수익은 0 (롱숏 모두 약간 낙관적).
- **컨센서스는 Yahoo 가 지금 저장한 값**이다 — 발표 당시 화면과 다를 수 있다. 매출 서프라이즈 없음.
- 업종은 오늘 기준 GICS, 편출 종목은 업종 없음.
- 비용: 편도 c bp × Σ|Δw| 만. 헤지 SPY 거래·차입비·시장충격 없음. 보유 중 비중 표류 재조정 무시.
- `overlay.event_table` 규칙상 데이터 **마지막 세션**이 반응일인 발표는 빠진다 — 실전 예측 당일 장전 발표는 하루 늦게 반영된다.
- 시도들은 서로 상관돼 있어 장부 행 수 N 은 독립 시도 수의 상한 — DSR 은 보수적이다.
