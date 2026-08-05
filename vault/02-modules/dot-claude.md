# .claude — AI 업무 자동화 체계

## 목적 / 역할

`.claude/`는 oursymbol 모노레포 루트에 있는 **Claude Code용 전사 AI 업무 자동화 디렉터리**다. 코드가 아니라 **업무 절차와 조직 지식을 텍스트로 정의해 AI에게 위임하는 계층**이다.

이 디렉터리의 존재 이유는 `.claude/memory/company/oao-ai-workflow.md`에 명시적으로 적혀 있다.

- OAO의 핵심 가치 중 하나가 "AI 기반의 효율" — 반복 작업을 AI에 넘기고 사람은 판단·창의에 집중한다.
- 조직의 병목은 대개 **사람 간 의존**("이건 A한테 물어봐야 해")이다. **동료에게 묻기 전에 AI에게 먼저 물어볼 수 있는 환경**을 만드는 것이 목표다.
- 이것이 가능하려면 AI가 쓸 맥락이 충분해야 한다. 그래서 회의록·기능 문서·의사결정 기록을 한 저장소에 모은다 — **"기록되지 않은 것은 존재하지 않는 것과 같다"**(OAO 핵심 가치).
- **스킬은 누구나 수정할 수 있다** — `.claude/skills/`는 텍스트 파일일 뿐이고, 고치면 팀 전체가 혜택을 본다.

즉 `.claude/`는 개발 보조 도구 설정이 아니라 **개발·기획·재무·운영을 아우르는 전사 업무 인터페이스**다. 실제로 27개 스킬 중 코드 작성 스킬은 하나도 없고, 대부분 데이터 조회·리포트·정산·문서화·계정 관리다.

## 하위 구조

```
.claude/
├── CLAUDE.md          # oh-my-claudecode(OMC) 보일러플레이트 — 아래 주의 참조
├── memory/            # 팀·회사·프로젝트 지속 지식
│   ├── people/        # 팀원 프로필 (4명)
│   ├── project/       # 아워심볼 서비스 비전
│   └── company/       # OAO 비전 + AI 업무 워크플로우 안내
├── hooks/
│   └── sync-env.sh    # SessionStart 워크트리 부트스트랩
└── skills/            # 슬래시 커맨드 27종
```

### `CLAUDE.md` (주의: 프로젝트 규칙 문서가 아니다)

`.claude/CLAUDE.md`는 **oh-my-claudecode(OMC)라는 서드파티 멀티에이전트 오케스트레이션 레이어가 자동 생성한 보일러플레이트**다. 파일 전체가 `<!-- OMC:START -->` / `<!-- OMC:END -->` 마커로 감싸여 있고, oursymbol 도메인 내용은 한 줄도 없다.

내용은 OMC 자체의 사용 규약이다 — 위임 우선(delegation-first) 철학, `autopilot`/`ralph`/`ultrawork` 실행 모드 키워드, 모델 라우팅(haiku/sonnet/opus), 33개 에이전트 카탈로그, "검증 없이 완료 선언 금지" 같은 규칙. 참조하는 `./shared/*.md`, `./MIGRATION.md` 파일들은 이 저장소에 존재하지 않는다(OMC 설치 경로에 있다).

**oursymbol 프로젝트의 실제 AI 협업 규칙은 저장소 루트의 `CLAUDE.md`**(「AI 협업 가이드」)에 있다. 아래 "핵심 규칙 / 가드레일"은 그쪽을 요약한 것이다.

### `memory/` — 팀·프로젝트 지식 저장소

스킬과 AI가 참조하는 데이터 소스. 코드에서 유도할 수 없는 조직 맥락을 담는다.

| 경로 | 내용 | 참조하는 곳 |
|------|------|-------------|
| `people/` | 팀원 프로필 4건. YAML frontmatter로 이름, 영문명, GitHub ID, 역할, `stt_variants`(회의 녹취 STT 오인식 변형) | `/start-work`, `/end-work`의 작업자 식별, `/create-meeting-notes`의 화자 매핑 |
| `project/oursymbol-vision.md` | 아워심볼 서비스 정의 — "스포츠 순간이 사회적으로 인정받는 구조". Respect Target / Contextual Audience / Recognition Space / Reaction 4요소 프레임과 현재 충족 수준·확장 방향 | 기능 기획 시 맥락 |
| `company/oao-vision.md` | OAO(On And Off) MISSION/VISION/CORE VALUES. 핵심 가치 6개: 완료 주의, 백워드 설계, 원팀, AI 기반의 효율, 회고, 기록 | 의사결정 맥락 |
| `company/oao-ai-workflow.md` | 전사 AI 업무 방식 안내서. 왜 AI를 쓰는지, 맥락 축적 4대 스킬(start-work / end-work / create-docs / update-context)의 선순환 구조, 스킬 카탈로그와 사용 예시 | 온보딩 문서. 루트 `CLAUDE.md`가 "AI 업무 워크플로우" 가이드로 직접 링크 |

`people/` 항목이 `stt_variants`(예: "성주님", "성준님")를 갖는 게 특징적이다 — 회의 녹취에서 이름이 잘못 받아적혀도 동일인으로 매핑하기 위한 필드로, 메모리가 실제 스킬 파이프라인의 입력임을 보여준다.

`.gitignore`에 `.claude/memory/gdrive/`가 제외되어 있어(로컬 스냅샷에는 없음), 구글 드라이브에서 내려받은 참조 자료를 메모리로 쓰는 경로도 상정되어 있다.

### `hooks/` — 세션 부트스트랩

`sync-env.sh` 한 개뿐이다. Claude Code **SessionStart**에 실행되는 bash 스크립트로, **git worktree에서 작업을 시작할 때 메인 워크트리의 환경을 끌어오는** 역할이다.

1. 현재 디렉터리가 메인 워크트리면 즉시 종료 (링크된 워크트리에서만 동작)
2. 메인 워크트리의 `.env*` 파일들을 찾아 현재 워크트리에 **심볼릭 링크** 생성 (`node_modules`, `build`, `.git`, `*.example` 제외)
3. `backend/services/*/node_modules`도 심볼릭 링크 (npm 설치가 느려서)
4. `pnpm-lock.yaml`이 있고 `node_modules`가 없으면 `pnpm install --frozen-lockfile` 실행
5. 무엇을 동기화했는지 한 줄 요약 출력

`.env` 파일은 gitignore 대상이라 새 워크트리에는 없다 — 이 훅이 그 간극을 메운다. 워크트리 기반 병렬 작업(`.claude/worktrees/`도 gitignore되어 있다)을 전제로 설계된 셈이다.

### `skills/` — 슬래시 커맨드 27종

각 스킬은 `skills/<이름>/SKILL.md` 한 파일이 본체이고, 필요하면 `scripts/`·`bin/`·`agents/`·`templates/` 보조 파일을 갖는다. 대부분 **목표 → 언제 사용하는가 → 안전 규칙 → 인자 파싱 → AI 수행 절차** 순의 공통 골격을 따른다.

#### 1. 업무 루틴 / 맥락 축적 (4)

`oao-ai-workflow.md`가 "가장 중요"하다고 지목한 축이다. 쓸수록 AI의 맥락 이해가 깊어지는 선순환을 노린다.

| 스킬 | 역할 |
|------|------|
| `/start-work` | 하루 시작. Slack 과거 메시지 + 회의록 액션 아이템을 읽어 업무 흐름 파악 → 브랜치 생성 → Slack 알림 |
| `/update-work` | 오늘 할 일 항목 추가/삭제 후 Slack 재전송 |
| `/end-work` | 하루 마무리. 커밋 내역과 계획 대비 실적 비교 → 커밋/PR 생성 → Slack 완료 알림 |
| `/clarify-thinking` | 소크라테스식 역질문으로 사용자의 의도·목적·핵심 아이디어를 좁혀준다 |

#### 2. 문서화 (4)

| 스킬 | 역할 |
|------|------|
| `/create-docs` | 인터뷰 기반 문서 생성. features / guides / brand / partnerships / planning / research / meetings 중 올바른 폴더에 배치 |
| `/create-meeting-notes` | 회의 transcript → 구조화된 국문/영문 회의록 |
| `/update-context` | `CLAUDE.md`·`README.md`·`docs/` 구조와 실제 파일의 불일치를 감지·수정 |
| `/create-presentation` | 프레젠테이션 파이프라인(리서치 → 자료 정리 → 디자인 → PPTX). 하위에 `agents/researcher.md`, `agents/organizer.md` 서브에이전트 프롬프트와 `templates/slide-content-schema.json` 보유 |

#### 3. 데이터 분석 (4)

BigQuery + RDS 조회 전용. 한국어 자연어로 물어보면 되고, **DB는 읽기만 하므로 안전**하다는 것이 전제다.

| 스킬 | 역할 |
|------|------|
| `/analyze` | 종합 대시보드(DAU/MAU + 매출 + 도네이션 + 지갑). 인자를 주면 자유형 쿼리 |
| `/analyze-user` | 유저 활동 — DAU, MAU, 리텐션, 세션, 화면 조회, 얼굴 검색 퍼널 |
| `/analyze-revenue` | 매출 — IAP, 인앱결제, 도네이션, 포인트 트랜잭션, 지갑 잔고, 파트너 정산 |
| `/analyze-advertisement` | 광고 성과 — 노출, 클릭, CTR, 게재 기간, ad_id별 분석 |

#### 4. 고객사 리포트 (2)

| 스킬 | 역할 |
|------|------|
| `/generate-organizer-report` | 이벤트 ID → 얼굴 검색/다운로드 데이터 + AI 코멘트 → `report.json` → S3 업로드 |
| `/generate-advertisement-report` | 광고주명 → RDS에서 광고 자동 탐색 + BigQuery 성과 → `report.json` → S3 업로드. 보조 스크립트 `build_report.py`, `build_demo.py`, `diagnose.py`, `update_index.py` 보유 |

리포트 생성 → 계정 생성(`/manage-business-account`) → URL/ID/PW 전달까지가 한 플로우로 정의되어 있다(목표 5분).

#### 5. 이벤트 데이터 수집·등록 (5)

| 스킬 | 역할 |
|------|------|
| `/crawl-marathon-kr` | roadrun.co.kr + runninglife.co.kr 교차검증 → 병합 Excel 출력 |
| `/crawl-marathon-jp` | runnet.jp 일본 대회 크롤링 |
| `/crawl-marathon-us` | 미국 대회 크롤링 |
| `/create-event` | 엑셀 파싱 → event-service API로 이벤트 + 앨범 일괄 생성. 다양한 엑셀 형식 자동 감지, 사용자가 고른 것만 생성 |
| `/backfill-event` | 비어있는 필드(`endsAt`, `lat`, `lng`, `regStartAt`, `globalRegionId` 등)를 웹 검색으로 찾아 채운다. UPDATE SQL은 **생성만** 하고 실행은 사용자 몫 |

크롤링과 등록이 분리되어 있고(`crawl-*` → Excel → `/create-event`), 사이에 사람의 확인이 들어간다.

#### 6. 계정 / 운영 (4)

| 스킬 | 역할 |
|------|------|
| `/manage-business-account` | 비즈니스 리포트 사이트 계정·권한 CRUD. S3의 `accounts.json`을 직접 고쳐 배포 없이 즉시 반영 |
| `/create-brand-photographer` | 브랜드/대회 파트너용 작가 계정 생성. 로고 R2 업로드 → photographer-service 관리자 API로 User + Photographer(ACTIVE) 원자 생성 → 실제 로그인까지 검증 |
| `/push-notification` | handleId로 유저 조회 → SQS → notification-service → FCM. 발송 전 사용자 확인 필수, prod는 이중 확인 |
| `/sync-instagram-post` | Prod `SocialPost`에서 해시태그/기간 조건으로 추출해 Dev `InstagramPost`로 넣는 INSERT SQL을 **파일로 생성만** 한다 (실행은 사용자) |

#### 7. 재무 / 정산 (3)

| 스킬 | 역할 |
|------|------|
| `/update-point-settlement` | 포인트 정산 엑셀 최신화. RDS에서 인앱결제·도네이션·정산을 자동 수집하고, 스토어 정산은 사용자 첨부 파일로 반영. `apple-appstore-정산-검증-가이드.md` 동봉 |
| `/add-photographer-settlement` | 신분증·통장사본 이미지/PDF에서 정보 추출 → 구글 드라이브 정산자료 폴더 업로드 → 작가 정산 마스터 시트에 행 추가. `scripts/upload_photographer_files.py`, `scripts/add_to_master_sheet.py` |
| `/update-finance` | 월별 재무 데이터. 세금계산서·급여대장·법인카드 파싱 → 드라이브 업로드 + 재무 대시보드 시트 갱신 |

이 3개는 개인정보·재무 데이터를 다루므로 산출물이 저장소가 아니라 **구글 드라이브/시트**로 나간다. `update-point-settlement/result/`는 `.gitkeep`만 남기고 내용물이 gitignore되어 있다.

#### 8. AI 인프라 (1)

| 스킬 | 역할 |
|------|------|
| `/symba-sync` | 로컬 Claude Code 자동 메모리를 맥미니의 **Hermes**에 SSH로 전달해 학습시킨다. 팀원 각자가 쌓은 노하우를 팀 공용 AI로 흡수시키는 경로 |

`/symba-sync`는 **민감도에 따라 수신처를 가른다** — 일반 맥락은 `default` 프로필(= Symba, 팀 공용, Slack 접근), 재무·세무·인사·정산·계좌·법무·개인 맥락은 `rafiki` 프로필(= Rafiki, 대표 전용)로 격리한다. 그리고 그 위에 **"계좌번호·비밀번호·토큰 같은 raw 시크릿은 어느 프로필로도 보내지 않는다(마스킹 또는 제외)"**는 규칙이 한 겹 더 있다. 첫 실행은 `--dry-run` 권장.

## 핵심 규칙 / 가드레일

> 출처는 저장소 루트 `CLAUDE.md`(「AI 협업 가이드」)와 각 SKILL.md의 "안전 규칙" 섹션이다.

### 기본 철학

- **사용자 주도** — 전략과 최종 의사결정은 사람이 한다
- **아키텍처 보호** — AI가 임의로 아키텍처나 중요 코드를 고치지 않는다
- **명시적 허가** — 사용자가 명확히 요청한 작업만 수행

파생 규칙: 이해 후 실행(목적·기존 구조 파악 → 영향 범위 분석), 범위 준수(임의 개선 금지), 복잡한 문제엔 대안 2개 이상 제시, 실패 시 강행하지 않고 상의, `package.json` scripts 먼저 확인.

### DB Read-Only (전역)

모든 DB(RDS, BigQuery, DynamoDB 등)에 대해 **데이터 변경·삭제 쿼리를 생성하지도, 실행하지도 않는다.**

- 금지: `INSERT` `UPDATE` `DELETE` `DROP` `ALTER` `CREATE` `TRUNCATE` `REPLACE` `RENAME` `GRANT` `REVOKE`
- 허용: `SELECT` `SHOW` `DESCRIBE` `EXPLAIN`
- 사용자가 수정을 요청해도 거절하고 DB 콘솔에서 직접 하도록 안내

이 규칙이 스킬 설계를 실제로 규정한다. `/backfill-event`와 `/sync-instagram-post`는 필요한 SQL을 **파일로 만들어 주고 실행은 사용자에게 넘기는** 우회 구조를 택했고, 그 사실이 스킬 설명에 명시되어 있다.

### 인프라 안전 규칙 (전역)

클라우드 파괴적 작업은 **반드시 사용자 확인 후** 실행한다.

- 확인 필수: Cloudflare R2 버킷/객체 삭제, DNS 변경, Workers 삭제 / AWS `delete-`·`terminate-`·`remove-`·`destroy` 계열, SG·VPC·RDS·ECS 삭제, IAM 정책 변경 / 프로덕션 리소스 변경 / 비용에 영향을 주는 변경
- 단독 허용: 조회·목록(`list`, `describe`, `get`), 상태 확인, 로그 조회, dev 환경 조회
- 사용자가 "삭제해", "진행해"라고 해도 **대상과 영향 범위를 먼저 요약**하고 확인받는다

### 스킬 레벨 공통 안전 패턴

27개 중 17개가 "안전 규칙" 섹션을 갖는다. 반복되는 패턴은 넷이다.

1. **쓰기는 사람에게 넘긴다** — SQL/변경사항을 생성만 하고 실행은 사용자
2. **외부에 나가는 것은 사전 확인** — 푸시 발송, 이벤트 생성, 계정 생성 전 확인
3. **prod는 이중 확인** — dev/prod 분기가 있는 스킬은 prod에서 한 번 더
4. **불확실성은 숨기지 않는다** — 웹 검색 결과가 불확실하거나 매핑 실패(예: userId 미매핑 → NULL)면 사용자에게 보고

### 코드베이스 탐색 / UI / 빌드 금지 사항

- 기존 코드 탐색 없이 구현 제안 금지, API 엔드포인트 URL 추측 금지, 관련 프로젝트를 전부 확인하기 전 단일 앱만 보고 판단 금지
- 디자인 시스템 확인 없이 코딩 시작 금지, 기존 컴포넌트 확인 없이 유사 컴포넌트 생성 금지, 하드코딩 값 금지(`bg-[#FF5733]` 등)
- 자동 빌드/린트 실행 안 함(요청 시만), TS/ESLint/Dart 오류 우회 금지, 프로덕션 배포는 사용자 승인 필수

## 다른 부분과의 관계

```
.claude/memory/          조직 지식 (누가·왜)
      │ 참조
      ▼
.claude/skills/          업무 절차 (어떻게)
      │ 호출
      ├──▶ backend/services/*   API 호출 (event, photographer, notification …)
      ├──▶ RDS / BigQuery       SELECT 전용
      ├──▶ S3 / R2 / Slack / Google Drive·Sheets
      └──▶ docs/                문서 생성·동기화 대상
```

- **`docs/`** — 가장 밀접하다. `/create-docs`가 `docs/` 하위에 문서를 만들고, `/update-context`가 `CLAUDE.md`·`README.md`·`docs/` 정합성을 점검한다. 루트 `CLAUDE.md`의 "docs/ 구조 가드"(서브디렉터리 금지, `YYMMDD-` 접두사 필수, 바이너리 커밋 금지 등)는 사실상 이 스킬들이 지켜야 할 계약이다. `/create-meeting-notes`는 `docs/meetings/`로, `/create-presentation`의 리서치는 `docs/research/`를 입력으로 삼는다.
- **`backend/`** — 스킬의 실행 대상. `/create-event`는 event-service API, `/create-brand-photographer`는 photographer-service 관리자 API, `/push-notification`은 SQS → notification-service, `/sync-instagram-post`는 `SocialPost`/`InstagramPost` 테이블을 다룬다. 즉 `.claude/skills/`는 백엔드의 **운영자용 프론트엔드 역할**을 텍스트로 대신한다.
- **`frontend/`** — 직접 참조는 거의 없다. 다만 `/manage-business-account`가 관리하는 계정은 `frontend/business/`(리포트 사이트)의 로그인 계정이고, `/create-brand-photographer`가 만드는 계정은 `frontend/studio/`로 로그인한다. 스킬이 프론트 제품의 **운영 백오피스**를 대체하고 있는 셈이다.
- **`research/`** — 구조는 닮았지만 성격이 다르다. `research/.claude/skills/`도 SKILL.md 형식이지만 그쪽은 `run.py` 드라이버가 headless로 호출하는 **배치 파이프라인 단계**이고(각 SKILL.md에 "사람 대화용 스킬이 아니다"라고 명시), `.claude/skills/`는 **사람이 슬래시 커맨드로 부르는 대화형 스킬**이다. 대회 데이터를 다룬다는 주제는 겹쳐서, `/crawl-marathon-*` + `/create-event`(수동 경로)와 `research/`(자동 경로)가 유사한 일을 서로 다른 방식으로 한다.
- **`.omx/`** — 보완 관계다. `.omx/plans/`는 **특정 기능 하나에 귀속된 일회성 설계 산출물**이고, `.claude/skills/`는 **재사용 가능한 절차**, `.claude/memory/`는 **지속적 조직 지식**이다. ([[omx]] 참조)
- **`.agents/skills/`** — `.claude/skills/`의 **부분 미러**다. 21개 파일이 있으나 `.claude/` 쪽 27개 중 일부(`add-photographer-settlement`, `backfill-event`, `crawl-marathon-*`, `create-brand-photographer`, `create-presentation`, `push-notification`, `symba-sync`, `sync-instagram-post`)가 빠져 있고, 이름이 같은 것들도 상당수 내용이 다르다. 루트 `AGENTS.md`(≈`CLAUDE.md`의 비-Claude 에이전트용 판본)와 짝을 이루는 구조로 보이나 동기화 방식은 문서화되어 있지 않다.
- **`.omc/`** — `.claude/CLAUDE.md`가 정의하는 OMC의 런타임 상태 디렉터리. `.gitignore`로 제외되어 있고 로컬 스냅샷에 없다.
- **서브디렉터리 `CLAUDE.md`** — `frontend/CLAUDE.md`, `backend/services/CLAUDE.md`가 해당 경로 작업 시 자동 로드된다. 이들은 핵심 요약이고, 상세 규칙은 `docs/guides/`에 있다는 계층 구조가 루트 `CLAUDE.md`에 명시되어 있다.

## 관찰 사항

- **`.claude/CLAUDE.md`가 프로젝트와 무관하다.** 전체가 OMC 보일러플레이트이고 oursymbol 내용이 없다. Claude Code는 `.claude/CLAUDE.md`가 아니라 루트 `CLAUDE.md`를 프로젝트 지침으로 읽으므로 동작상 문제는 없지만, 파일명만 보고 접근하면 잘못된 문서를 읽게 된다.
- **훅 등록 위치가 저장소에 없다.** `sync-env.sh`는 SessionStart 훅이라고 주석에 적혀 있으나 이를 등록하는 `settings.json`이 커밋되어 있지 않다. `.gitignore`가 `.claude/settings.local.json`을 제외하므로 각자 로컬에 설정하는 구조로 보인다 — 즉 **새 팀원은 훅이 자동으로 켜지지 않는다.**
- **일부 SKILL.md에 DB 접속 자격증명이 평문으로 커밋되어 있다.** 3개 스킬의 "DB 접속 정보" 표에 dev/prod DB의 host·port·user·password가 그대로 적혀 있다(구체 값은 이 문서에 옮기지 않음). 로컬 SSH 터널 경유 접속을 전제한 것으로 보여 실효 위험은 낮을 수 있으나, 저장소에 평문으로 남는 형태다.
- **크롤링 스킬의 git 추적 기준이 갈린다.** `.gitignore`가 `crawl-marathon-jp/`와 `crawl-marathon-us/`를 "Claude skills (local only)"로 통째 제외하는 반면 `crawl-marathon-kr/`는 추적된다. 세 스킬 모두 목적이 같은데 kr만 공유 대상인 이유가 문서화되어 있지 않다.
- **루트 `CLAUDE.md`의 스킬 표가 실제 디렉터리와 어긋난다.** 표에 `backfill-event`, `update-finance`, `symba-sync` 3개가 빠져 있고 `/update-work`는 두 번 나온다. `/update-context`가 바로 이런 불일치를 잡기 위한 스킬이라는 점에서 아이러니한 상태다.
- **AI 인프라가 이중화되어 있다.** 로컬 Claude Code(`.claude/`)와 맥미니의 Hermes/Symba/Rafiki가 별개로 존재하고 `/symba-sync`가 그 사이를 잇는다. 후자는 이 저장소가 아니라 `symba/` 디렉터리와 맥미니의 `~/oursymbol-platform/`에 있다.

## 관련 문서

- [[repo-map]]
- [[project-summary]]
- [[omx]]
- [[research]]
