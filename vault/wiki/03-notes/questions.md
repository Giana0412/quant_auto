---
created: 2026-08-05
updated: 2026-08-05
---

# Questions & Ambiguities

구조가 애매하거나 확인이 필요한 항목을 여기에 축적합니다. 각 항목은 어느 모듈 문서화 과정에서 나왔는지 표시합니다.

## [research] 소스 확장(source-discovery)의 주간 cron이 어디에 등록되는지 불명

`research-source-scout` 스킬과 `run.py`(`SOURCE_DISCOVERY_STAGE`, "별도 경로 — STAGES(매일)엔 안 넣음, 주 1회 별도 cron")는 소스 확장 스테이지가 **주 1회 별도 cron으로 호출된다**고 기술한다. 그러나 커밋된 `research/crontab`에는 매일 05:00 풀 run 한 줄만 있고 주간 엔트리가 없다.
→ 주간 실행이 (a) 아직 미구현인지, (b) 맥미니 호스트 launchd나 컨테이너 밖에서 별도로 돌고 있는지, (c) 수동 실행만 하고 있는지 확인 필요. `sources.yml`에 `added_via: auto` 항목이 2026-07-20~21자로 다수 있어 실제로 돈 적은 있어 보인다.

## [research] README §2 디렉터리 트리가 실제 파일 목록과 불일치

README의 디렉터리 트리에 다음이 빠져 있다.
- `.claude/skills/`를 "파이프라인 스킬 3종"으로 적었으나 실제로는 5종 (`research-source-scout`, `research-source-vet` 누락)
- `scripts/verify_run.py`, `scripts/fetch_render.py` 누락 (둘 다 2026-07-26 추가)
- `sources.yml`, `.gitignore` 누락

→ README를 갱신할 대상인지, 아니면 트리는 의도적으로 요약본인지 확인 필요.

## [research] `vault/wiki/01-architecture/repo-map.md`의 `research/` 설명이 틀린 것으로 보임

repo-map.md는 `research/`를 "시장 분석 및 연구 자료"로 적고 있으나, 실제 `company-src/oursymbol/research/`는 이벤트 자동 수집 배치 파이프라인이다. "시장 분석 및 연구 자료"는 `company-src/oursymbol/docs/research/`(다른 디렉터리)에 해당한다.
→ repo-map.md 수정이 필요해 보이나, 이번 작업 범위 밖이라 손대지 않았다.

## [research] README §7 마일스톤 체크박스가 실제 운영 상태와 어긋남

§7에서 M1~M5가 전부 미완료(`[ ]`)로 표시돼 있으나, 다른 문서 근거는 이미 실운영 중임을 시사한다.
- `.env.example`: `RESEARCH_DRY_RUN=0` + "2026-07-24 실반영 운영 전환"
- README §9: 최근 7일 크론 실행 중 발생한 실사고 기록
- `sources.yml`: 실제 run이 자동 갱신한 흔적

→ 마일스톤 체크박스를 갱신해야 하는지, 아니면 M1~M5 정의가 체크박스보다 넓은 범위인지 확인 필요.

## [research] `RESEARCH_MAX_NEW_EVENTS` 기본값과 명시된 팀 방침이 다름

`.env.example`의 주석은 "준범님 방침: 하루 20건 정도"라고 적혀 있으나 실제 값은 `RESEARCH_MAX_NEW_EVENTS=5` / `RESEARCH_MAX_RECHECK=5`다.
→ 5는 검증 단계의 임시값이고 20이 목표인지, 아니면 방침이 5로 바뀌었는지 확인 필요. (실제 맥미니의 `data/.env` 값은 git에 없어 확인 불가)

## [research] paused 16개 소스의 재개 조건·주체가 명시돼 있지 않음

`sources.yml` 헤더에 "RUNNING 4개(hardcoded 파서)가 실DB에서 안정화된 뒤 카테고리/소스 확장을 재개한다"고만 적혀 있다.
→ "안정화"의 판정 기준(기간·정확도 지표 등)과, 재개를 누가/어떻게 트리거하는지(수동으로 `paused`→`active` 편집인지, 자동 승격 경로가 있는지)가 문서화돼 있지 않다. `evaluate_trial_promotions()`는 `trial`만 검사하므로 `paused`는 자동으로 돌아오지 않는다.

## [research] README §6 요구사항 `Event.lastResearchedAt` 갱신이 미구현 상태

README §6은 "조사 시마다 `Event.lastResearchedAt` 갱신"을 출력 계약으로 명시하지만, §9 백로그에 "파이프라인이 한 번도 안 씀(`apply_verdicts`/`apply_auto_updates`/`process_holds` 어디도 안 써줌)"으로 기록돼 있다.
→ 문서화 시 §6을 "설계상 요구사항"으로 볼지 "현재 동작"으로 볼지 애매하다. 본 모듈 문서에서는 §6 표를 API 계약으로만 옮기고 `lastResearchedAt` 갱신은 기술하지 않았다.

## [omx] `.omx`라는 이름의 유래와 공식 정의가 저장소 어디에도 없음

`CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/guides/` 어디에도 `.omx` 디렉터리의 존재·목적·사용 규칙에 대한 설명이 없다. 목적은 내용물로부터 역추론한 것이다.
- `.omx`가 무엇의 약자인가? (`.omc`(oh-my-claudecode)와 이름이 비슷한데 의도적으로 파생시킨 것인지, 무관한지)
- 어떤 작업에서 `docs/features/` 대신 `.omx/plans/`에 문서를 써야 하는지 판단 기준이 있는지
- 이 디렉터리를 만든 도구/에이전트가 정해져 있는지 (Codex? 특정 스킬?)

## [omx] `docs/features/`에서 참조하는 계획 파일이 로컬에 존재하지 않음

`docs/features/260503-challenge-submission-mvp.md`가 "Canonical Plan"으로 지목한 `.omx/plans/20260503-social-submissions-url-submit-plan.md`가 실제로는 없다. 현재 `.omx/plans/`에는 `20260429-app-campaign-detail-page-review-plan.md` 1개 파일뿐이다.
- 아직 작성되지 않은 것인지, 작성 후 삭제/이동된 것인지, 아니면 개인 로컬에만 있고 커밋되지 않은 것인지 확인 필요.
- 만약 계획 문서가 커밋되지 않는 게 정상 워크플로우라면, 지금 `.omx/`가 git 추적 대상인 것과 모순된다.

## [omx] 계획 문서의 "원본 문서"도 존재하지 않음

`20260429-app-campaign-detail-page-review-plan.md` 헤더가 원본으로 지목한 `docs/features/260428-app-campaign-detail-page.md`가 `docs/features/`에 없다. 삭제됐는지, 다른 이름으로 통합됐는지(예: `260503-challenge-submission-mvp.md`로 대체) 확인 필요.

## [omx] 계획 문서 상태가 `draft`인데 구현은 이미 진행됨

문서 상태는 `draft`이고 §10에 미결 논점(`slug` 재도입 여부, `instagram-service` 서비스 경계 재정리 여부)이 남아 있으나, `backend/services/challenge-service/`와 migration SQL 3종은 이미 존재한다.
- 구현 완료 후 계획 문서 상태를 갱신하는 규칙이 있는지 (`docs/features/`는 `상태: 진행중 → 완료` 갱신 규칙이 CLAUDE.md에 명시되어 있으나 `.omx/`에는 그런 규칙이 없음)
- §10 보류 항목들이 실제로 어떻게 결론났는지 문서에 반영할 주체가 누구인지

## [omx] 계획 문서 내부 링크가 개인 로컬 절대 경로로 박혀 있음

코드 참조가 `/Users/<사용자>/Workspace/oursymbol/backend/...` 형태의 머신별 절대 경로여서 다른 환경에서는 깨진다. 저장소 상대 경로로 통일할지, 아니면 계획 문서는 원래 개인 작업물이라 그대로 두는지 방침 확인 필요.

## [claude] `.claude/CLAUDE.md`가 프로젝트 규칙이 아니라 OMC 보일러플레이트임

`.claude/CLAUDE.md`는 전체가 `<!-- OMC:START -->`/`<!-- OMC:END -->`로 감싸인 oh-my-claudecode 자동 생성 문서이고, oursymbol 도메인 내용이 한 줄도 없다. 참조하는 `./shared/agent-tiers.md`, `./MIGRATION.md` 등은 이 저장소에 존재하지 않는다. 실제 프로젝트 AI 협업 규칙은 저장소 루트 `CLAUDE.md`에 있다.
→ (a) 의도적으로 OMC를 팀 표준으로 도입한 것인지, (b) 특정 개인이 로컬에 설치한 흔적이 커밋된 것인지 확인 필요. 후자라면 파일명이 루트 `CLAUDE.md`와 같아 혼동을 유발하므로 정리 대상일 수 있다. 본 모듈 문서에서는 "OMC 보일러플레이트"로 명시하고 규칙 요약은 루트 `CLAUDE.md`를 출처로 삼았다.

## [claude] `hooks/sync-env.sh`를 등록하는 설정 파일이 저장소에 없음

스크립트 주석은 "Runs on Claude Code SessionStart"라고 명시하지만, 이를 훅으로 등록하는 `.claude/settings.json`이 커밋되어 있지 않다. `.gitignore`는 `.claude/settings.local.json`을 제외한다.
→ 각자 로컬 `settings.local.json`에 수동 등록하는 구조라면 **새 팀원 환경에서는 훅이 자동으로 켜지지 않는다.** 공유용 `settings.json`을 커밋할지, 아니면 온보딩 문서에 수동 설정 절차를 넣을지 확인 필요.

## [claude] 일부 SKILL.md에 DB 접속 자격증명이 평문으로 커밋되어 있음

3개 스킬의 "## DB 접속 정보" 표에 dev/prod DB의 host·port·user·password가 평문으로 적혀 있다(값은 vault 문서에 옮기지 않음). 로컬 SSH 터널 경유(127.0.0.1)를 전제한 것으로 보여 실효 위험은 낮을 수 있으나, 저장소 히스토리에 남는다.
→ 의도된 것인지(터널이 없으면 무의미한 값이라 허용), 아니면 환경변수/`.env` 참조로 바꿔야 하는지 확인 필요. 특히 `/symba-sync` 스킬은 "raw 시크릿은 어느 프로필로도 보내지 않는다"는 규칙을 명시하고 있어 방침이 서로 어긋나 보인다.

## [claude] 크롤링 스킬 3종의 git 추적 기준이 갈림

`.gitignore` 최상단이 "Claude skills (local only)"로 `crawl-marathon-jp/`와 `crawl-marathon-us/`를 통째 제외하는데 `crawl-marathon-kr/`는 추적된다. 세 스킬 모두 목적·구조가 같다.
→ jp/us가 (a) 아직 검증 안 된 실험 단계라 제외한 것인지, (b) 특정 개인 전용이라 제외한 것인지, (c) 단순히 정리가 안 된 것인지 확인 필요.

## [claude] `.agents/skills/`와 `.claude/skills/`의 동기화 주체·주기가 불명

`.agents/skills/`는 `.claude/skills/`의 부분 미러다. `.claude/` 27개 중 8개(`add-photographer-settlement`, `backfill-event`, `crawl-marathon-*`, `create-brand-photographer`, `create-presentation`, `push-notification`, `symba-sync`, `sync-instagram-post`)가 `.agents/`에 없고, 이름이 같은 것들도 상당수 내용이 다르다(`diff -rq` 기준 10건 이상).
→ (a) 어느 쪽이 정본인지, (b) 동기화가 수동인지 스크립트가 있는지, (c) `.agents/`에 일부만 두는 것이 의도적 선별(비-Claude 에이전트에는 민감 스킬 미노출)인지 확인 필요. 루트 `CLAUDE.md`·`AGENTS.md` 어디에도 `.agents/`에 대한 설명이 없다.

## [claude] 루트 `CLAUDE.md`의 스킬 표가 실제 `.claude/skills/`와 불일치

표에서 누락: `backfill-event`, `update-finance`, `symba-sync` (실제 디렉터리에는 존재). 중복: `/update-work`가 두 번 나온다. 표 기준 24종(중복 제외) vs 실제 27종.
→ `/update-context` 스킬이 바로 이런 불일치를 잡기 위한 것이므로 한 번 돌리면 될 것으로 보이나, 로컬 전용 스킬(jp/us)은 의도적으로 표에 남겨둔 것인지 등 판단이 필요해 손대지 않았다.

## [frontend] `pnpm-workspace.yaml`에 존재하지 않는 `frontend/push` 패키지가 등록돼 있음

`pnpm-workspace.yaml`의 packages 목록에 `frontend/push`가 있으나 해당 디렉터리가 없다. 루트 `package.json`에도 `dev:push`/`build:push` 스크립트는 없다.
- 삭제된 프로젝트의 잔재인지, 아직 만들지 않은 예정 프로젝트인지 확인 필요.
- 만약 삭제된 것이라면 `office`의 `/push` 라우트(푸시 발송 화면)로 흡수된 것인지 — 그렇다면 workspace 항목을 제거해야 한다.

## [frontend] `checkin` 앱이 상위 문서 어디에도 등재돼 있지 않음

`frontend/checkin/`(QR 현장 체크인, dev 포트 8070)은 실제로 존재하고 workspace·루트 스크립트에도 등록돼 있지만 문서에는 빠져 있다.
- 루트 `CLAUDE.md`의 "프로젝트 구성" 표에 없음
- 루트 `CLAUDE.md`의 "크로스 프로젝트 의존성" 표에 없음 (어떤 backend 서비스를 호출하는지 미기재. `.env.example`에 `VITE_COMMERCE_API_URL`이 있어 commerce-service로 추정만 가능)
- `frontend/CLAUDE.md`의 React 프로젝트 목록(`event/`, `business/`, `office/`, `together/`, `studio/`)에도 없음
- `README.md`가 없는 유일한 React 프로젝트

→ 신규 프로젝트라 문서 반영이 안 된 것인지, 아니면 임시/실험 프로젝트라 의도적으로 뺀 것인지 확인 필요. `landing`도 `frontend/CLAUDE.md`의 React 규칙 목록에서 빠져 있다(크로스 의존성 표에는 있음).

## [frontend] `landing`의 backend 의존성 기술이 실제 코드와 어긋남

루트 `CLAUDE.md` 크로스 의존성 표는 `landing`을 "없음 (GA4 트래킹만)"으로 적고 있으나, 실제로는:
- `landing/.env.example`에 `VITE_API_URL`, `VITE_API_KEY`, `VITE_PHOTOGRAPHER_API_URL`, `VITE_PHOTOGRAPHER_API_KEY` 4개 변수가 있고
- `landing/api/og/photographer.ts` Vercel Function이 `/photographer/@:handleId` 요청을 받아 작가 정보를 조회해 OG 메타를 생성한다.

→ 표를 갱신해야 하는지, 아니면 해당 기능이 비활성 상태인지 확인 필요.

## [frontend] `event/`에 `netlify.toml`과 `vercel.json`이 공존

실제 배포는 Vercel(`event.o-sym.com`)인데 `netlify.toml`(SPA fallback 리다이렉트)도 남아 있다. 과거 Netlify 배포 잔재로 보이나, 아직 병행 운영 중인 환경이 있는지 확인 필요.

## [frontend] 라우터/린터 이원화의 통일 시점이 미정

`frontend/CLAUDE.md`에 "향후 TanStack Router로 통일 예정"이라고만 적혀 있다. 현재 상태:
- TanStack Router + Biome: `office`, `studio`, `business`, `checkin`
- react-router-dom + ESLint: `event`, `landing`, `together`

→ 통일 대상·시점·담당이 정해져 있는지, 신규 프로젝트는 무조건 TanStack Router+Biome로 시작하면 되는지 확인 필요. Tailwind 버전도 같은 선으로 갈린다(v4 vs v3).

## [frontend] Flutter 앱 SDK 제약이 Dart 2에 묶여 있음

`app/pubspec.yaml`의 `environment.sdk`가 `>=2.18.6 <3.0.0`이다. Dart 3 이상에서는 이 제약으로 빌드가 막힌다.
- 의도적으로 Dart 2에 고정한 것인지, 갱신을 안 한 잔재인지 확인 필요.
- 팀에서 실제로 사용하는 Flutter/Dart 버전이 무엇인지 (`.metadata` 외에 명시된 곳이 없다)

## [frontend] `shared/src/ui/`가 사실상 비어 있음

`@oursymbol/shared`의 `./ui` export는 주석에 "공통 UI 컴포넌트로 확장 가능"이라고만 적혀 있고 실제로는 `cn` 유틸 재export 1줄이다. 공용 디자인 시스템은 각 앱의 로컬 `components/ui/`(shadcn 스타일)에 중복 존재한다.
- 공용 컴포넌트를 `shared`로 올리려던 계획이 중단된 것인지, 아니면 앱별 디자인이 달라 의도적으로 분리 유지하는 것인지 확인 필요.
- `business`/`checkin`/`landing`은 `@oursymbol/shared`에 아예 의존하지 않는데, 이것도 의도인지.

## [frontend] 잔재로 보이는 파일들

- `app/archive.zip` (448B) — 무엇인지 불명. Git에 커밋돼 있다.
- `studio/src/metadata.old.json` (235B) — `.old` 접미사로 보아 잔재.

→ 삭제 가능한지 확인 필요.

## [docs] `docs/ir/`가 CLAUDE.md 문서 구조에 등재되어 있지 않음

`docs/ir/`는 334개 파일로 `docs/` 전체(544개)의 61%를 차지하는 최대 카테고리인데, `CLAUDE.md`의 "문서 구조" 트리(227~244행)에도 `/create-docs` 스킬의 카테고리 표에도 없다.
- 의도적으로 규칙 바깥에 둔 예외인지, 아니면 `CLAUDE.md` 갱신이 누락된 것인지 확인 필요.
- 등재한다면 `/create-docs`가 IR 문서를 어떤 파일명 규칙으로 생성해야 하는지도 정의가 필요하다.

## [docs] `docs/ir/`가 구조 가드 1번·5번을 위반한 상태

- **가드 1(서브디렉터리 금지)**: `ir/` 아래에 `pitchdeck/`, `v1/`, `v2/`, `v3/`가 있고 그 아래 다시 `assets/`, `appendix_image2/`, `소풍/`이 있어 2단계 깊이다. 가드 1의 예외 목록(`gdrive/`, `personal/`, `projects/`, `meetings/internal/`, `meetings/external/`)에 `ir/`는 없다.
- **가드 5(바이너리 금지)**: `.pdf` 10개, `png/jpg/jpeg` 312개가 커밋되어 있다. 규칙대로면 Google Drive 보관 대상이다.

IR 덱을 HTML+에셋으로 관리하는 방식 자체가 예외로 승인된 것인지, 아니면 정리 대상인지 판단 필요. 승인된 예외라면 가드 1·5의 예외 목록에 `ir/`를 추가해야 한다.

## [docs] `docs/planning/`의 서브디렉터리가 예외 목록에 없음

`planning/2026-Q2-seanergy-island/`와 `planning/2026-Q2-seeding/` 두 폴더가 가드 1번(서브디렉터리 금지) 예외 목록에 없다. 두 폴더 모두 `README.md` + `YYMMDD-` 문서 구조로 `projects/` 패턴을 따르고 있다.
- 2026-07에 도입된 `docs/projects/`로 이관해야 하는 대상인지, 아니면 `planning/`도 프로젝트성 묶음을 허용하는지 확인 필요.
- 폴더명 규칙도 `projects/`(`<프로젝트명>/`)와 달리 `YYYY-Qn-<주제>` 형식이다.

## [docs] `features/260523-auth-ssot-routes.csv` — 가드 5번이 금지한 `.csv`

`docs/` 하위에서 허용되지 않은 확장자를 쓰는 유일한 파일이다(`terms/*.txt`는 명시적 예외). Google Drive로 옮길지, 마크다운 표로 변환할지, 아니면 소규모 라우트 목록은 예외로 둘지 방침 확인 필요.

## [docs] CLAUDE.md가 존재하지 않는 가이드 문서를 링크함

`CLAUDE.md` 288행이 `./docs/guides/face-engine-guide.md`("자체 얼굴 검색 엔진 — AdaFace + pgvector 운영 가이드, 엔진 선택, 배포, 트러블슈팅")를 링크하지만 해당 파일이 없다. `guides/`의 face 관련 파일은 `face-image-bulk-deletion-guide.md` 하나뿐이다.
- 문서가 아직 작성되지 않은 것인지(링크 선반영), 삭제·이동된 것인지 확인 필요. 관련 내용은 `features/260522-custom-face-engine-migration.md` 등에 흩어져 있는 것으로 보인다.

## [docs] `features/`의 `상태:` 값이 표준화되어 있지 않음

`CLAUDE.md`는 `상태: 진행중 → 완료` 전이만 규정하는데, 실제 값은 `완료`(24) `진행중`(9) 외에 `설계`, `기획중`, `운영중`, `구현 완료`, `구현완료`, `완료 (dev 배포)`, `운영중 (dev/prod 배포 완료, office 연동 진행중)` 등 서술형까지 섞여 있다.
- 허용 값을 열거형으로 고정할지, 자유서술을 유지할지 결정 필요. 고정한다면 `설계`/`기획중` 같은 착수 전 단계와 `운영중` 같은 완료 후 단계를 포함할지도 함께 정해야 한다.

## [docs] 카테고리별 최신성 편차 — 중단된 것인지 관행이 바뀐 것인지

`features/`(~260803), `projects/`(~260802), `qa/`(~260724)는 활발한 반면 `meetings/`(~260528), `brand/`(~260320), `partnerships/`(~260318)는 수개월째 갱신이 없다.
- 특히 `meetings/`는 43건 중 42건이 `[KO]`/`[EN]` 이중언어 정형 문서로 잘 관리되다가 5월 말 이후 멈췄다. 회의 자체가 줄어든 것인지, 회의록을 다른 곳(Drive, Notion 등)에 남기기 시작한 것인지 확인 필요.
- `partnerships/`의 내용이 2026-07 도입된 `projects/`로 흡수되는 흐름인지도 함께 확인하면 좋겠다.

## [docs] `partnerships/`의 날짜 접두사 없는 한글 파일명

`채널A-하트시그널러닝페스타-계약서-draft.md`, `대회촬영-OURSYMBOL-서비스-계약서-template.md` 2개가 `YYMMDD-` 접두사 없이 한글 파일명을 쓴다(나머지 2개는 규칙 준수).
- `partnerships/`는 가드 4번의 날짜 필수 목록(`features/`, `planning/`, `meetings/`)에 없어 형식적 위반은 아니다. 다만 계약서 템플릿처럼 시점이 없는 문서를 어느 폴더에 어떤 이름으로 둘지 규칙이 비어 있다 — `guides/`처럼 "영구 문서는 날짜 없음" 원칙을 적용할지 확인 필요.

## [backend] 자격증명이 저장소에 평문으로 커밋되어 있음 (우선 확인 필요)

문서화 중 발견한 사항으로, 값 자체는 이 vault 어디에도 옮기지 않았다.

- 여러 서비스의 `serverless.yml` `custom.database` 블록에 **DB 호스트·계정·비밀번호가 평문**으로 들어 있다 (dev/prod 모두). 해당 서비스들은 `.env`나 SSM을 쓰지 않고 이 값을 그대로 Lambda 환경변수로 주입한다.
- `backend/services/commerce-service/toss_credential.txt`가 **git에 추적되고 있다**(`git ls-files`로 확인). 결제 PG 자격증명으로 보이는 파일명이다.
- 반면 `backend/services/CLAUDE.md`는 "`.env` 파일 Git 커밋 금지, 환경 변수 하드코딩 금지"를 규칙으로 명시하고 있어 **규칙과 실제 상태가 정면으로 어긋난다**.

→ (a) 이미 로테이션된 폐기 값인지, (b) 살아 있는 값이라 즉시 교체·이력 정리가 필요한지 확인 필요. 살아 있다면 SSM Parameter Store(이미 일부 서비스가 `@aws-sdk/client-ssm`으로 사용 중)로 통일하는 것이 자연스러워 보인다.

## [backend] `event-service/README.md`의 내용이 다른 서비스 문서임

`event-service/README.md`가 `kor-triathlon-image-service/README.md`와 **바이트 단위로 같은 내용**("한국 트라이애슬론 이미지 서비스")이다. 복사 후 갱신을 잊은 것으로 보인다.
→ event-service용 README를 새로 쓸 대상인지, 아니면 `event-service/docs/`(README.md, event-domain-concept.md, module-design.md 등 7개 파일)가 이미 그 역할을 하므로 최상위 README를 삭제하면 되는지 확인 필요.

## [backend] 서비스 목록 문서 3곳이 서로, 그리고 실제와 불일치

실제 배포 스택은 19개인데 어느 문서도 전체를 담고 있지 않다.

| 문서 | 누락된 서비스 |
|------|--------------|
| 루트 `CLAUDE.md` "Backend 서비스 목록" | crew, challenge, instagram, business, face-engine |
| `backend/services/AGENTS.md` "독립 서비스" 표 | crew, notification, challenge, instagram, business, face-engine |
| `backend/services/README.md` "마이크로서비스" 목록 | 위보다 더 많이 누락 (7개만 등재) |

→ 세 문서 중 어느 것을 SSOT로 삼을지 정하고 나머지는 링크로 대체하는 편이 나아 보인다. 특히 `README.md`는 Serverless 공식 템플릿 보일러플레이트(`AWS NodeJS Example`)가 상단에 그대로 남아 있어 정리 대상으로 보인다.

## [backend] `business-service`가 병렬 배포 대상에도 제외 목록에도 없음

`scripts/deploy-parallel.js`의 `SERVICES` 배열은 16개이고, `AGENTS.md`는 제외 대상으로 `face-engine-service`, `image-resize-lambda` 2개만 명시한다. `business-service`는 **양쪽 어디에도 없다** — 즉 `pnpm deploy:dev:parallel`로는 절대 배포되지 않는데 그 사실이 문서화돼 있지 않다.
→ 의도적 제외(수동 배포)인지 단순 누락인지 확인 필요. 의도라면 `AGENTS.md` 제외 목록에 추가해야 한다.

## [backend] `challenge-service`와 `instagram-service`의 경계가 불명확

두 서비스가 상당 부분 겹친다.

- 공통: `campaign` 개념, 제출물(submission) CRUD, 캠페인 리포트(`getCampaignReport` / `getCampaignUserStats` / `getCampaignCrewStats` / `getCampaignLogs` — **함수명까지 동일**), `apify-client`를 통한 인스타 수집, `ssmService.ts`, `verificationService.ts`
- 차이: `instagram-service`는 OAuth 토큰 관리·미디어 조회를 갖고, `challenge-service`는 SQS 배치 자동수집(`autoCollection/`)과 R2 미디어 저장을 갖는다

`.omx` 문서화 과정에서도 계획 문서 §10의 미결 논점으로 "`instagram-service` 서비스 경계 재정리 여부"가 이미 지적된 바 있다([[omx]] 참조).
→ challenge-service가 instagram-service를 대체하는 중인지(그렇다면 instagram-service 폐기 시점), 아니면 "인스타 연동"과 "챌린지 도메인"으로 영구 분리할 것인지 확인 필요.

## [backend] `business-service`만 인증 체계 밖에 있음

19개 스택 중 `business-service`만 `auth-common` 플러그인을 쓰지 않고, S3의 `accounts.json`을 읽어 자체적으로 로그인을 처리한다(계정별 password/role/permissions를 담은 JSON). VPC에도 붙지 않는다.
- 전사 인증 SSOT 원칙(`serverless.yml`의 `auth.type`)에서 의도적으로 예외를 둔 것인지, 아니면 초기 프로토타입이 그대로 굳은 것인지 확인 필요.
- `/manage-business-account` 스킬이 이 `accounts.json`을 CRUD하는 구조라, 운영 편의를 위한 의도적 설계일 가능성도 있어 보인다.

## [backend] SQL 마이그레이션의 적용 이력을 추적하는 장치가 없음

- 마이그레이션 러너가 없다 — `package.json`에 migrate 스크립트가 없고, `schema_migrations` 같은 이력 테이블도 저장소 어디에서도 참조되지 않는다. `mysql` 클라이언트로 사람이 직접 `source` 하는 방식이다.
- 따라서 **어떤 환경에 몇 번까지 적용됐는지 코드로는 알 수 없다.**
- 파일명 규칙도 갈린다: 대부분 `NNN_설명.sql`, `commerce-service`만 `설명_YYYYMMDD.sql`.
- `prod_global_all.sql`이 최상위/advertisement/feed 등 여러 곳에 중복 존재한다 — 글로벌화 때의 묶음 스크립트로 보이나 어느 것이 정본인지 불명.

→ 적용 이력을 관리하는 별도 수단(운영 위키, 스프레드시트 등)이 있는지, 없다면 러너 도입 계획이 있는지 확인 필요.

## [backend] 다수 서비스에서 dev와 prod가 같은 리소스를 가리킴

여러 `serverless.yml`의 `custom` 블록에서 이미지 버킷의 `dev`와 `prod` 값이 **동일한 `*-dev` 버킷**으로 지정돼 있다 (`sessionImageBucket`, `crewSymbolImageBucket`, `eventImageBucket` 등이 여러 서비스에서 반복).
→ prod 사진이 실제로 dev 버킷에 쌓이고 있는 것인지, 아니면 별도 경로 분리가 코드 레벨에서 이뤄지는지 확인 필요. 의도적이라면 이유를(비용? 이관 미완?) 문서에 남길 필요가 있어 보인다.

## [backend] 얼굴 엔진 이원화의 종료 조건이 정해져 있지 않음

`faceEngine` 필드 유무로 Rekognition과 자체 pgvector 엔진이 앨범 단위로 갈린다. 현재는 크루 신규 앨범만 pgvector이고 이벤트 앨범·기존 앨범은 Rekognition이다.
- 기존 앨범을 pgvector로 **소급 인덱싱할 계획이 있는지**, 아니면 영구 병행인지
- 이벤트 앨범을 언제 전환하는지 (사진 볼륨은 이벤트 쪽이 훨씬 클 것으로 보임)
- 전환 완료 판정 기준과 Rekognition 폐기 시점

→ `face-engine-service/README.md`는 성능·정확도 검증 결과까지는 상세히 남겼으나 이관 로드맵은 없다. 루트 `CLAUDE.md`가 링크하는 `docs/guides/face-engine-guide.md`는 [[docs]] 문서화 과정에서 **파일이 존재하지 않음**이 확인됐으므로, 그 문서가 작성되면 여기 답이 담길 가능성이 있다.

## [backend] 저장소가 S3와 Cloudflare R2로 이원화된 상태의 정리 방침

신규 경로(face-engine, crew-service, photographer-service, challenge-service)는 Cloudflare R2를, 기존 경로는 AWS S3를 쓴다. R2 도입 동기는 egress 무료로 보인다.
→ S3를 단계적으로 걷어내는 방향인지, 용도별로(원본은 S3 / 배포용은 R2 등) 영구 분담시키는 것인지 확인 필요. `image-resize-lambda`(S3+CloudFront 온디맨드 리사이즈)와 face-engine의 사전 3벌 리사이즈(R2)가 **같은 문제를 다른 방식으로 풀고 있어**, 어느 쪽이 현행 표준인지도 함께 확인이 필요하다.
