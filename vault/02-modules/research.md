# research — 이벤트 리서치 자동화 파이프라인

> 대상 경로: `company-src/oursymbol/research/` (읽기 전용)

## 1. 목적 / 역할

스포츠 대회(마라톤·트레일런·철인3종·사이클·배드민턴 등) 정보를 **매일 자동으로 수집·보강·심사해 Event DB에 반영하는 배치 파이프라인**이다.

- 기존에 사람이 수동으로 돌리던 `/crawl-marathon-kr` + `/create-event` 스킬 작업을 무인화한 것
- 대화형 에이전트가 아니라 **"매일 새벽 깨어나는 배치 워커"** — 사내 대화형 AI(Symba/Hermes)와 별개로 동작
- 사내 맥미니(`Symba.local`)의 3번째 Docker 컨테이너로 상주하며, cron이 매일 05:00 KST에 1회 실행

### 핵심 설계 원칙: "LLM은 판단만, 반영은 코드가"

| 역할 | 담당 |
|------|------|
| 웹페이지 이해·필드 매핑·신뢰도 판단 | LLM CLI (headless `claude -p` / `codex`) → JSON 아티팩트 산출 |
| API 호출·멱등성·중복 방지·가드 | Python 드라이버 `scripts/run.py` |

LLM이 event-service API나 DB를 직접 만지는 경로는 **존재하지 않는다**. 골격(스케줄→큐→API)은 정형이므로 Python으로 git 관리하고, 알맹이(제각각인 대회 페이지 해석)만 LLM에 위임하는 구조다. (2026-07-10 팀 합의로 n8n 대신 이 구조 채택 — 기존 n8n 워크플로우의 로직은 폐기가 아니라 이 구조로 이관)

### 파이프라인 5단계

```
cron 05:00 KST
   ↓
scripts/run.py (드라이버)
   ├─ ① discover    → LLM: 애그리게이터에서 신규 대회 발견 + 재조사 대상 선별
   ├─ ② enrich      → LLM: 공식 상세페이지 크롤링해 스키마 필드 추출·보강
   ├─ ③ adjudicate  → LLM: auto / hold / reject 신뢰도 심사
   ├─ ④ 반영         → 드라이버가 직접 event-service API 호출 (LLM 아님)
   ├─ ⑤ 상태 관리    → SQLite (중복키·재조사큐·보류큐·run 이력·실행시간)
   └─ ⑥ 보고         → Slack (수집 요약 / 승인 요청 / 실패 알림)
```

별도 경로로 **소스 확장** 스테이지(`source-discovery`)가 있다. 주 1회 cadence로 scout(새 애그리게이터 후보 발견) → vet(심사) 을 돌려 `sources.yml`을 자동 갱신한다.

---

## 2. 하위 구조

```
research/
├── README.md            # 온보딩 문서 (설계 배경·마일스톤·알려진 이슈)
├── Dockerfile           # 툴체인 이미지 (node22 + claude/codex CLI + python venv)
├── docker-compose.yml   # 컨테이너 정의 (3g / 2cpu, healthcheck)
├── entrypoint.sh        # crontab 등록 후 cron 포그라운드 상주
├── crontab              # 매일 05:00 KST 풀 run
├── .env.example         # 시크릿 템플릿 (실제 값은 data/.env, git 제외)
├── .gitignore           # data/, __pycache__ 제외
├── sources.yml          # 크롤 대상 소스 목록 (설정으로 분리)
├── scripts/             # Python 드라이버 및 보조 도구
└── .claude/skills/      # LLM이 따르는 스테이지별 지시문 + JSON 출력 계약
```

### 컨테이너/배포 파일

| 파일 | 설명 |
|------|------|
| `Dockerfile` | **툴체인만** 담는다. `node:22-bookworm-slim` 기반 + python3/cron/git + `@anthropic-ai/claude-code`·`@openai/codex` 글로벌 설치 + venv(requests, beautifulsoup4, boto3, openpyxl). 파이프라인 코드는 마운트된 모노레포 clone에서 실행되므로 **코드 수정에는 재빌드가 필요 없다** |
| `docker-compose.yml` | 컨테이너 정의. `./data`(런타임)와 `./data/oursymbol`(모노레포 clone)을 마운트, `mem_limit: 3g` / `cpus: 2.0`, TZ=Asia/Seoul, 1시간 간격 healthcheck |
| `entrypoint.sh` | 기본 CMD가 `cron`이면 환경변수를 `/opt/data/.cron-env`로 덤프(cron 작업에 전달용)하고 crontab 등록 후 `cron -f`로 상주. 그 외 인자는 그대로 실행 |
| `crontab` | `0 5 * * *` — 매일 05:00에 `run.py`를 실행하고 `/opt/data/logs/run.log`에 append |

### `scripts/` — Python 드라이버 및 보조 도구

| 파일 | 규모 | 역할 |
|------|------|------|
| `run.py` | ~3,800줄 | **파이프라인 본체 드라이버.** 스테이지 오케스트레이션, SQLite 스키마 관리, LLM CLI 호출 및 스트림 계측, DB 스냅샷 동기화, 중복 판별(dedup), 지오코딩, R2 포스터 업로드, event-service API 반영, Slack 알림까지 전부 담당 |
| `verify_run.py` | ~200줄 | **run 자가검증 리포트.** 산출물과 라이브 DB 실제 저장값을 대조하고, 모든 시각을 KST로 정규화해 보여준다(DB는 UTC 저장이라 raw로 보면 착시 발생). 이상 항목에 자동 플래그를 달아 상단으로 올림. `{run_dir}/verify_report.md` 출력 |
| `fetch_render.py` | ~220줄 | **SPA 공식페이지 렌더 헬퍼.** sixshop·imweb 같은 웹빌더 SPA는 직접 GET하면 가시 텍스트가 거의 없어 grounding에 실패한다. jina Reader의 브라우저 엔진(headless 크로미움)으로 렌더한다. 렌더 백엔드를 이 파일 한 곳에 모아 교체 가능하게 설계 |
| `healthcheck.py` | ~30줄 | 마지막 **성공** run이 26시간을 넘으면 exit 1(unhealthy). daily 05:00 기준 26h = 1회 누락 시 감지. state.db가 없으면 healthy로 간주 |
| `backfill_timings.py` | ~210줄 | 일회성 백필. 과거 `run.log` 텍스트를 파싱해 `stage_timings`를 채운다. 백필 행은 `detail`에 `{"backfilled": true}`가 있어 실측과 구분 가능 |

`run.py`의 주요 기능 블록:

- **state** — SQLite 스키마 정의/마이그레이션 (`db()`)
- **실행시간 계측** — `timed_stage()`, `stage_timings`/`step_timings` 기록
- **DB 스냅샷 동기화** — `sync_events_seen()`, `sync_organizations_seen()`. LLM이 DB에 직접 접근하지 않도록 기존 이벤트/조직을 JSON 파일로 떠서 넘긴다
- **LLM 스트림 계측** — `_StreamParser`, `_run_claude_stream()`. `--output-format stream-json`으로 돌려 도구 호출별 소요를 드라이버 시계로 측정
- **LLM 러너** — `run_stage_llm()`. 스테이지별 러너(claude/codex)와 timeout 적용
- **중복 판별** — `dedup_discovered_new_events()`, `find_exact_duplicate()`, 제목 정규화·날짜·장소 매칭
- **반영** — `apply_verdicts()`(신규 생성), `apply_auto_updates()`(기존 수정), `apply_discipline_updates()`(종목 추가), `process_holds()`(보류 큐 + Slack 승인요청)
- **부가 처리** — `geocode_venue()`/`resolve_region()`(지오코딩·지역 매핑), `upload_poster_to_r2()`(포스터 업로드), `find_or_create_organization()`
- **소스 확장** — `run_source_discovery()`, `evaluate_trial_promotions()`, `sources.yml` 로드/저장

### `.claude/skills/` — LLM 스테이지 지시문

각 스킬은 frontmatter + 마크다운 지시문 + JSON 출력 계약으로 구성된다. **사람 대화용이 아니라 드라이버가 headless로 호출**하는 프롬프트다.

| 스킬 | 규모 | 역할 |
|------|------|------|
| `research-discover` | ~380줄 | ① 탐색. `sources.yml`의 active 소스를 크롤해 신규 대회 발견 + 재조사 대상(recheck) 선별. 카테고리 정책(Category 마스터 keyCode 매핑, 우선순위)도 여기에 정의 |
| `research-enrich` | ~760줄 | ② 크롤링. 공식 상세페이지에서 스키마 필드 추출. **grounding 필수** — 원문을 `enrich_raw/`에 저장하고 다시 열어서만 추출(기억/추론으로 채우기 금지), 포스터 이미지 vision 판독 포함 |
| `research-adjudicate` | ~210줄 | ③ 심사. enrich 결과를 `auto`(자동 반영) / `hold`(사람 검토) / `reject`(폐기)로 분류. 기존 수동 파이프라인에서 사람이 하던 확인을 대체 |
| `research-source-scout` | ~100줄 | (소스 확장) ① 후보 발견. 기존 소스에 없는 새 애그리게이터 URL을 찾는다. **판단은 하지 않는다** — 놓치지 않고 모으는 역할 |
| `research-source-vet` | ~210줄 | (소스 확장) ② 심사. 후보를 시험 크롤해 `auto_approve`/`hold`/`reject` 판정. 잘못 승인하면 나쁜 데이터가 영구히 흘러들어오므로 이벤트 adjudicate보다 보수적 기준 |

### `sources.yml` — 크롤 대상 소스 목록

**새 소스 추가 시 이 파일만 고치면 되는 것이 설계 목표** (run.py/스킬 코드 수정 불필요). 2026-07-21부터 `source-discovery` 스테이지가 자동 갱신한다.

소스별 필드:

| 필드 | 값 |
|------|-----|
| `status` | `active`(정식 운영) / `trial`(신규, 검증 중) / `paused`(보류, 크롤 제외) / `rejected`(폐기) |
| `category` | Category 마스터의 keyCode — `RUNNING`, `TRAIL_RUNNING`, `TRIATHLON`, `FITNESS`, `CROSSFIT`, `CYCLING`, `BADMINTON` |
| `fetch_method` | `direct`(그냥 GET) / `jina_proxy`(JS 렌더링 필요한 SPA용 프록시) |
| `extraction` | `hardcoded`(사람이 짠 전용 파서) / `generic_llm`(전용 파서 없음, trial 기본값) |
| `added_via`, `trial_runs`, `notes` | 자동 추가 이력 및 검증 메모 |

현재 상태: **active 4개**(marathongo, runninglife, gorunning, roadrun — 전부 RUNNING/hardcoded), **paused 16개**. paused 16개는 2026-07-24 실반영 전환 시점에 "RUNNING 4개가 실DB에서 안정화된 뒤 확장을 재개한다"는 점검 회의 결정으로 일괄 보류된 상태다.

### `.env.example` — 설정 키 (값은 절대 커밋되지 않음, `data/.env`로 복사해 사용)

카테고리별 키 이름만 정리한다. 값은 이 문서에 기록하지 않는다.

| 그룹 | 키 |
|------|-----|
| LLM 인증 | `CLAUDE_CODE_OAUTH_TOKEN` (Max 구독 사용). ⚠️ `ANTHROPIC_API_KEY`는 **넣으면 안 된다** — 구독 대신 API 과금으로 빠짐 |
| event-service | `EVENT_SERVICE_URL`, `EVENT_SERVICE_TOKEN` (출력 계약, admin 인증) |
| office-service | `OFFICE_API_URL`, `OFFICE_API_KEY` — dedup 스냅샷 출처. event-service는 PUBLISHED만 돌려줘서 DRAFT를 못 보기 때문 |
| prod 읽기전용 | `EVENT_SERVICE_URL_PROD`, `EVENT_SERVICE_TOKEN_PROD` — 중복 방지 전용. GET 외 사용 없음(코드로 보장) |
| 알림 | `SLACK_WEBHOOK_URL` |
| 자산 처리 | `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`(포스터 업로드), `KAKAO_REST_API_KEY`(지오코딩), `JINA_API_KEY`(SPA 렌더) |
| 동작 제어 | `RESEARCH_DRY_RUN`, `RESEARCH_MAX_NEW_EVENTS`, `RESEARCH_MAX_RECHECK`, `RESEARCH_STREAM_TIMING`, `STAGE_RUNNER_{DISCOVER,ENRICH,ADJUDICATE}`, `STAGE_TIMEOUT_ENRICH` |
| 경로/기타 | `OFFICE_BASE_URL`, `RESEARCH_DATA_DIR`, `RESEARCH_REPO_DIR` |

### `data/` — 런타임 (git 제외, 맥미니 전용)

`.env`, `state.db`(SQLite), `runs/{run_id}/`(스테이지별 JSON 아티팩트·`enrich_raw/`·`*_events.jsonl`·`timings.json`·`verify_report.md`), `logs/run.log`, `oursymbol/`(모노레포 전용 clone).

---

## 3. 다른 부분과의 관계

### 3.1 backend — event-service (출력 계약, 유일한 쓰기 경로)

**모든 반영은 event-service API로만 이뤄진다. DB 직접 접근은 금지.**

| 목적 | 엔드포인트 |
|------|-----------|
| 이벤트 생성/수정 | `POST /events`, `PUT /events/{id}` |
| 조직 find-or-create / 검색 | `POST /organizations`, `GET /organizations?q=` |
| 이벤트-조직 연결 (HOST/OPERATOR/SPONSOR) | `POST /events/{id}/organizations` |
| 종목 조회/생성/수정 | `GET`·`POST /events/{id}/disciplines`, `PUT .../{disciplineId}` |

- 이 파이프라인이 만든 이벤트는 `sourceSystem=RESEARCH`, 승인 전 `lifecycle=DRAFT`
- 종목 표준코드는 `5K/10K/HALF/FULL/ULTRA/ETC`
- 드라이버는 `Category`, `GlobalRegion`, `Organization` 등 백엔드 도메인 테이블 구조에 의존한다 (루트 `CLAUDE.md`의 엔티티 관계 문서 참조)

**하드 가드** (프롬프트가 아니라 `run.py` 코드에 구현):
1. PUT 바디에 `sourceSystem`을 절대 포함하지 않는다 (ORGANIZER 마커 덮어쓰기 방지)
2. disciplines는 upsert (GET → type+name 매칭 → PUT/POST) — DB에 UNIQUE 제약이 없어 재조사 시 중복 생성됨
3. 중대 필드(날짜·접수기간·장소) 실질 변경은 confidence와 무관하게 hold로 강등
4. 자동 수정 이력은 `event_update_audit` 테이블에 old_value와 함께 남겨 롤백 가능

### 3.2 backend — office-service

`GET /office/events`(x-api-key)를 **읽기 전용**으로 사용한다. event-service `/events`는 `lifecycle=PUBLISHED`만 돌려줘서, 이미 DRAFT로 존재하는 대회를 discover가 신규로 다시 만들 위험이 있었기 때문. 미설정 시 event-service로 폴백(PUBLISHED만, 경고 로그).

### 3.3 frontend — office (관리자 콘솔)

**승인 UI 역할.** Slack에는 인바운드가 없고, 실제 승인/수정은 사람이 office에서 한다.

- 신규 발견 → 전부 DRAFT 생성 → Slack 요약 + office 링크 → **승인 = office에서 PUBLISHED 전환**
- 기존 수정 보류 건 → Slack에 "현재값 → 제안값 + 근거" 발송 → 사람이 office에서 직접 수정 → 다음 run이 감지해 큐 정리
- 드라이버는 `OFFICE_BASE_URL`(기본 `https://office.o-sym.com`)로 `/events/{id}` 링크를 조립해 Slack 메시지에 붙인다

### 3.4 `.claude/skills/` (모노레포 루트) — 수동 스킬의 계승 관계

| 기존 수동 스킬 | 이 파이프라인에서 |
|---|---|
| `/crawl-marathon-kr` | discover 스테이지로 무인화 |
| `/create-event` | enrich + adjudicate + 드라이버 반영으로 분해 |
| `/crawl-marathon-jp`, `/crawl-marathon-us` | M5(해외 소스 확장)의 시드 자산으로 예정 |

enrich 스테이지는 기존 `create-event` 스킬과 **동일한 R2·Kakao 키를 재사용**한다(포스터 업로드·지오코딩).

### 3.5 인프라 — 맥미니 컨테이너 3형제

| 컨테이너 | 용도 | 자원 |
|---|---|---|
| hermes | Symba·Rafiki (회사 대화형 AI) | 6g |
| eros | 개인 실험 AI | 4g |
| **research** | 이 파이프라인 | 3g / 2cpu |

컨테이너·데이터·자원 한도 모두 독립이며, Hermes 게이트웨이를 거치지 않는다. 배포 위치는 맥미니의 `~/oursymbol-platform/research/`(모노레포 안). 호스트 launchd(`com.oao.research-pull`)가 main을 자동 pull하므로 **컨테이너는 git을 만지지 않는다**.

**코드 반영 흐름**: 로컬 개발 → PR → main 머지 → 미니의 clone 자동 pull → 다음 run부터 반영. 이미지 재빌드는 `Dockerfile` 변경 시에만 필요.

### 3.6 Slack

파이프라인의 유일한 아웃바운드 알림 채널(`SLACK_WEBHOOK_URL`). 수집 시작/완료 리포트, 최소 DRAFT 생성 결과, 자동 업데이트 변경 내역(전→후 diff), 승인 요청 블록, 중복 차단·날짜 이상 알림, run 완료 요약(소요·비용 포함), 실패 알림을 발송한다.

---

## 4. 운영 참고

### 실행 명령

```bash
# 컨테이너 기동
docker compose up -d --build

# 수동 1회 실행 (dry-run: API 반영 없이 아티팩트만)
docker exec research python3 /opt/oursymbol/research/scripts/run.py --dry-run

# 특정 스테이지만 (개발용)
python3 run.py --stage discover
python3 run.py --from-run <RUN_ID>   # 기존 run 폴더 재사용

# 결과 확인
tail -f data/logs/run.log
python3 scripts/verify_run.py [run_id]
```

### SQLite 상태 테이블 (`data/state.db`)

| 테이블 | 담기는 것 |
|--------|-----------|
| `events_seen` | dedup_key(정규화 제목+날짜) ↔ event_id 매핑 |
| `research_queue` | 재조사 큐 (우선순위: 임박 > 접수중 > 먼 미래) |
| `pending_changes` | 보류 큐. `UNIQUE(event_id, field, proposed)`로 같은 건 재질문 방지 |
| `runs` | run 이력 (started/finished, status, discovered/created_count/held/failed) |
| `applied_events` | apply가 실제 생성한 이벤트 |
| `event_update_audit` | 자동 수정 이력 (old_value 보존 → 롤백용) |
| `stage_timings` | 스테이지별 소요·건수·outcome·LLM 비용·토큰 |
| `step_timings` | 도구 호출 단위 소요 + `llm_thinking`(모델 생성 대기 구간) |

### 러너 전략

`.env`의 `STAGE_RUNNER_{DISCOVER|ENRICH|ADJUDICATE}`로 스테이지별 LLM을 교체할 수 있다. M1 검증 단계는 전부 `claude`(Max 구독), M2 이후 discover/enrich는 `codex`(ChatGPT 구독)로 옮기고 adjudicate만 claude 유지가 계획.

### 마일스톤 (README §7 기준)

- [x] M0 런타임 합의 (2026-07-10)
- [ ] M0.5 n8n export 마이닝 + admin 서비스 토큰 발급
- [ ] M1 discover 단일 소스 E2E
- [ ] M2 enrich 신 스키마 매핑 + `apply_verdicts` 구현
- [ ] M3 adjudicate + Slack 리포트 + pending_changes
- [ ] M4 재조사 큐 + cron 상시화 + 심사 정확도 리뷰 → auto ON 결정
- [ ] M5 소스 확장 (국내 검증 후 북미·일본)

---

## 5. 관련 문서

- `company-src/oursymbol/research/README.md` — 원본 온보딩 문서 (설계 배경·알려진 이슈 백로그)
- `company-src/oursymbol/CLAUDE.md` — 도메인 지식 (Category/Region 테이블 구조, 백엔드 서비스 목록)
- [[repo-map]] · [[project-summary]] · [[questions]]
