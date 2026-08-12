---
created: 2026-08-05
updated: 2026-08-05
---

# docs/ — 문서 허브

## 목적 / 역할

`company-src/oursymbol/docs/`는 모노레포 루트의 **팀 전체 문서 저장소**다. 개발 규칙부터 기능 명세, 회의록, IR 자료, 프로젝트 아카이브까지 코드가 아닌 모든 지식이 한 곳에 모인다.

성격을 규정하는 세 가지:

- **거의 전부 Git 추적 대상이다.** 로컬 스냅샷 기준 544개 파일 중 544개가 `git ls-files docs`에 잡힌다. 예외는 `.gitignore`로 제외된 `docs/personal/*`와 `docs/gdrive/*` 둘뿐이며, 두 폴더 모두 `.gitkeep`만 남긴 빈 상태다.
- **읽기 전용 참조가 아니라 개발 프로세스의 입력이다.** 루트 `CLAUDE.md`는 "필수 탐색 순서" 2번에 `docs/features/` 확인을 넣어두고, "`docs/features/`의 문서는 기능 구현의 **입력(spec)**이다"라고 명시한다. 구현 중에는 문서의 체크리스트를 갱신하고, 완료 시 헤더의 `상태:`를 바꾸는 것까지가 워크플로우에 포함된다.
- **구조 자체가 강제 규칙의 대상이다.** `CLAUDE.md`에 "docs/ 구조 가드 (필수 — 커밋 전 반드시 검증)" 6개 항목이 있고, 위반 시 **커밋/PR 진행을 중단**하도록 되어 있다. 이 정도로 구조를 규범화한 디렉터리는 저장소 내에서 `docs/`가 유일하다.

## 카테고리별 요약

13개 하위 폴더. 파일 수는 로컬 스냅샷 기준이다.

| 폴더 | 파일 수 | 담는 것 | 파일명 규칙 | 날짜 범위 |
|---|---|---|---|---|
| `ir/` | 334 | IR 덱·밸류에이션·피치덱 자료 | 혼재 (아래 참조) | 260528~260618 |
| `features/` | 85 | 기능 명세, PRD, API 설계, 마이그레이션 계획 | `YYMMDD-` 필수 | 251224~260803 |
| `meetings/` | 43 | 회의록 (`internal/` 31, `external/` 12) | `YYMMDD-` 필수 | 260305~260528 |
| `guides/` | 16 | 개발 규칙·워크플로우 (영구 참조) | `<주제>-guide.md`, **날짜 접두사 금지** | — |
| `planning/` | 15 | BM·사업 전략, 로드맵 | `YYMMDD-` 필수 | 260320~260523 |
| `terms/` | 13 | 약관 원문 | `<종류>[-<로케일>].txt` + README | — |
| `projects/` | 13 | 프로젝트 단위 아카이브 (폴더별) | `YYMMDD-` 필수 (README 제외) | 260717~260802 |
| `research/` | 10 | 시장 분석·벤치마킹·플레이북 | `YYMMDD-` | 260319~260622 |
| `qa/` | 7 | QA 결과·테스트 핸드오프 | `YYMMDD-` | 260512~260724 |
| `partnerships/` | 4 | 파트너십 리서치·제안서·계약서 draft | 혼재 (아래 참조) | 260317~260318 |
| `brand/` | 2 | 대외 콘텐츠 (인터뷰, 브런치) | `YYMMDD-` | 260316~260320 |
| `personal/` | 1 | 개인 메모 — **gitignored**, `.gitkeep`만 존재 | `YYMMDD-` | — |
| `gdrive/` | 1 | Google Drive 원본 rclone 다운로드 대상 — **gitignored**, `.gitkeep`만 존재 | — | — |

### `features/` — 기능 명세 (85)

가장 활발한 카테고리이자 개발 워크플로우의 중심. 문서 헤더가 정형화되어 있다:

```
> **작성일**: 2026-08-03
> **상태**: 완료 | 진행중 | 설계 | 기획중 | 운영중 …
> **카테고리**: features
> **관련 서비스**: donation-service, frontend/app …
```

`상태:` 필드는 47개 문서에서 파싱되며 `완료` 24건, `진행중` 9건이 주류다. 다만 값이 자유서술이라 `구현 완료`/`구현완료`/`완료 (dev 배포)`/`운영중 (dev/prod 배포 완료, office 연동 진행중)`처럼 표기가 갈린다 — 열거형이 아니라 관습이다.

내용 스펙트럼이 넓다. 순수 PRD(`260702-moment-ticket-module.md` — 도메인 개념 재정의)부터 장애 사후 분석 겸 이관 계획(`260803-iap-appstore-server-api-migration.md` — StoreKit 2 breaking change로 인한 영수증 검증 실패 근본 원인 추적)까지 포함한다. 즉 "기능 명세"라는 이름보다 **엔지니어링 의사결정 기록** 전반을 담는 쪽에 가깝다.

251224 파일(`251224-studio-foundation.md`) 하나만 2025년이고 나머지는 전부 2026년 — 사실상 2026년 들어 본격 운영되기 시작한 관행이다.

### `guides/` — 개발 규칙 (16)

`CLAUDE.md`가 "**`docs/guides/`는 서브디렉토리 CLAUDE.md의 상세 버전이다**"라고 정의한다. `frontend/CLAUDE.md`·`backend/services/CLAUDE.md`가 경로 진입 시 자동 로드되는 핵심 요약이라면, guides는 그 뒤의 상세 규칙·패턴을 담는다.

날짜 접두사를 쓰지 않는 유일한 `.md` 카테고리다. 이는 명시적 규칙(가드 3번)이며, 근거는 "날짜 접두사가 붙은 문서는 `features/`에 속할 가능성이 높다" — 즉 **영구 규칙(guides) vs 시점 기록(features)** 을 파일명으로 구분하는 장치다.

내용 축은 셋으로 나뉜다:
- 기술 스택: `flutter-guide`, `react-vite-guide`, `backend-serverless-guide`, `monorepo-guide`, `coding-style-guide`
- 인프라·배포: `vercel-guide`, `universal-link-guide`, `env-management-guide`, `mac-mini-access-guide`, `rclone-google-drive-guide`
- 운영·업무: `photographer-payment-guide`, `shinhan-bulk-transfer-guide`, `face-image-bulk-deletion-guide`
- AI 관련: `ai-codebase-exploration-guide`, `ai-safety-guide`

마지막 축이 흥미로운데, 코드 가이드와 **AI 에이전트 행동 가이드**가 같은 폴더에 공존한다. `.claude/`가 실행 가능한 스킬을 담는다면 `guides/`는 사람과 AI가 함께 읽는 산문 규칙을 담는 셈이다.

### `meetings/` — 회의록 (43)

`CLAUDE.md` 가드 1번의 서브디렉터리 금지 예외로, `internal/`(31) · `external/`(12) 2분할만 허용된다.

- `internal/`: 정기 `YYMMDD-weekly.md`(11건 확인)와 비정기 주제 회의(`260327-push-notification-policy`, `260507-1on1-sangwook-feedback` 등)가 섞인다. 1on1도 여기 들어간다.
- `external/`: 파트너·고객·자문 미팅. 파일명에 상대방 이름이 들어간다(`260407-nasmedia-partnership-meeting`, `260408-iseongpil-point-settlement-tax-consultation`).

**43건 중 42건이 `[KO]`/`[EN]` 섹션을 병기한 이중언어 문서**다. 헤더에 일시·소요시간·참석자·회의 유형을 표로 두고, `## [KO] 1. 결정사항` / `## [KO] 2. 액션 아이템` 구조를 따른다. 이 정형성은 `/create-meeting-notes` 스킬(transcript → 구조화된 국문/영문 회의록)이 생성하기 때문으로 보인다.

원문 트랜스크립트·녹취는 Git이 아닌 Google Drive에 두는 것이 규칙이다.

### `ir/` — IR 자료 (334, 전체의 61%)

파일 수 기준 압도적 1위이면서 **`CLAUDE.md`의 문서 구조 트리에도, `/create-docs` 스킬의 카테고리 표에도 등재되어 있지 않은** 폴더다. 사실상 규칙 바깥에서 자라난 영역이다.

구성:

```
ir/
├── 260528-ir-deck-blueprint.md       # 덱 설계
├── 260528-ir-reference-guide.md
├── 260528-ir-valuation-analysis.md   # 밸류에이션
├── pitchdeck/  (105)  260618-ir-pitchdeck.html + assets/ appendix_image2/ 소풍/
├── v1/         (51)   260604-ir-deck-v1.html + assets/
├── v2/         (65)   260611-ir-deck-v2.html + appendix_image2/ assets/
└── v3/         (110)  260615-ir-deck-v3.html + 5개 md(데이터 요약·그래프 데이터·슬라이드 가이드) + assets/ 소풍/
```

파일 타입 내역: `png` 265, `jpg` 35, `jpeg` 12, `pdf` 10, `md` 8, `html` 4. 즉 **334개 중 322개가 이미지·PDF**이고, 실제 문서는 12개뿐이다. IR 덱을 HTML로 작성하고 그 에셋을 함께 커밋하는 방식이며, `v1 → v2 → v3 → pitchdeck` 버전 스냅샷을 통째로 보존한다.

이 구성은 `CLAUDE.md` 가드 1번(서브디렉터리 금지)과 5번(바이너리 금지 — `.pdf`, `.png`은 Drive 보관)을 정면으로 위반한다. 자세한 논점은 아래 [관찰 사항](#관찰-사항) 참조.

민감도: 밸류에이션·투자 관련 내용이 포함된 영역이므로 이 문서에서는 구조만 기술하고 수치·조건은 옮기지 않는다.

### `projects/` — 프로젝트 아카이브 (13)

가장 최근(2026-07~08)에 도입된 카테고리로, 커밋 `2d3a793d`("docs(ganggun): 강군 프로젝트 아카이브 신설 + docs/projects 구조 도입")에서 시작됐다.

기존에는 하나의 프로젝트 문서가 성격별로 `brand/`·`partnerships/`·`planning/`에 흩어졌는데, 이를 **프로젝트 단위로 묶는** 것이 도입 취지다(가드 2번: "성격별 폴더로 흩어뜨리지 않는다").

현재 3개 프로젝트:
- `ganggun/` — 국방부 하이브리드 피트니스 레이스 (브랜드 코어, 종목 구성, 견적, 네이밍 피드백)
- `kolmar/` — 콜마글로벌 협업 (킥오프, 제안서 draft, 바우처 전략)
- `tips/` — TIPS R&D 과제 (타당성 방어, 보안 계획, 데이터 소스 검증)

규칙이 가장 촘촘하다(가드 6번): 폴더는 1단계까지만, `README.md` 필수(개요·현황·Drive 원본 위치 명시), 나머지 문서는 `YYMMDD-` 접두사 필수, 바이너리·회의 원문은 여기에도 금지. 실제 `ganggun/README.md`는 개요 표 / 참여사 역할 표 / 의사결정 라인 / 현황(날짜 명기) 구조를 갖추고 개별 문서로 링크를 건다.

### `terms/` — 약관 원문 (13)

`README.md` 1개 + `.txt` 12개. `.txt` 확장자를 쓰는 이유가 명시적 예외로 등록되어 있다(가드 5번: 바이너리 금지 "예외: `docs/terms/*.txt`").

파일명은 `<종류>[-<로케일>].txt` — `service.txt` / `service-en.txt` / `service-ja.txt`처럼 한/영/일 3개 로케일을 병렬로 둔다. 로케일 파생이 있는 것은 `service`, `privacy`, `marketing` 3종이고, `partner-service` · `donation-partner` · `settlement`(작가 대상)은 국문만 있다.

**Git이 정본이 아니다.** README가 "DB(`Terms` 테이블)가 실제 서비스에 노출되는 원본이며, 이 디렉토리는 약관 변경 이력 추적과 리뷰를 위한 문서 원본"이라고 선을 긋는다. 워크플로우는 파일 수정 → PR 법적 검토 → 머지 후 DB `Terms` INSERT → 파일 헤더 메타데이터 갱신 순이다. README에 파일↔`Terms.type`↔버전↔시행일 매핑 표가 있어 동기화 상태를 추적한다.

### `planning/` · `research/` · `qa/` · `partnerships/` · `brand/`

- **`planning/`** (15) — BM·사업 전략. 루트에 8개 `.md`가 있고, 나머지는 `2026-Q2-seanergy-island/` · `2026-Q2-seeding/` 두 서브폴더에 묶여 있다. 이 서브폴더들은 가드 1번의 예외 목록에 없다(아래 관찰 사항). 폴더에는 `README.md`를 두고 공모 메타·일정·평가표·파일 목록을 정리하는 `projects/`와 유사한 패턴을 쓴다.
- **`research/`** (10) — 시장 분석·벤치마킹·플레이북. 외부 미팅에서 얻은 지식을 재사용 가능한 형태로 정제한 문서가 많다(`260319-brand-building-playbook.md`는 헤더에 출처 미팅·참석자·용도를 명시). 도네이션 정산 세무 검토, EXIF 샘플링처럼 기술·회계 리서치도 섞인다.
- **`qa/`** (7) — QA 결과와 핸드오프. 헤더에 작성일·브랜치·상태·코드 리뷰 여부를 두고, 대응하는 `features/` 문서와 짝을 이루는 경우가 많다(예: `qa/260521-event-photographer-pre-registration-qa.md` ↔ `features/260521-event-photographer-pre-registration.md`).
- **`partnerships/`** (4) — 리서치·제안서·계약서 draft. 4개 중 2개는 날짜 접두사 없이 한글 파일명을 쓴다(`채널A-하트시그널러닝페스타-계약서-draft.md`, `대회촬영-OURSYMBOL-서비스-계약서-template.md`). 계약서 템플릿류는 시점 문서가 아니어서 날짜를 붙이지 않은 것으로 보이나 규칙에 명시된 예외는 아니다.
- **`brand/`** (2) — 대외 콘텐츠. 언론 인터뷰와 브런치 글 목록(외부 링크 인덱스)만 있는 최소 카테고리다.

## 문서화 규칙 (CLAUDE.md "docs/ 구조 가드")

`CLAUDE.md` 246~264행. **위반 상태에서 커밋 금지**이며, 위반 발견 시 커밋/PR을 중단하고 사용자에게 올바른 위치를 제안하도록 되어 있다.

| # | 규칙 | 요지 |
|---|---|---|
| 1 | **서브디렉터리 금지** | 각 하위 폴더는 플랫(파일만). 예외: `gdrive/`, `personal/`, `projects/`, `meetings/internal/`, `meetings/external/` |
| 2 | **문서 위치 적합성** | 폴더별 허용 유형 준수. 특히 `guides/`는 영구 규칙만, 기능 설계는 `features/` |
| 3 | **guides/ 날짜 금지** | `guides/`에 `YYMMDD-` 파일명 사용 금지 |
| 4 | **날짜 접두사 필수** | `features/`, `planning/`, `meetings/`의 `.md`는 `YYMMDD-` 필수 |
| 5 | **바이너리 금지** | `.pdf .docx .hwp .pptx .ppt .xls .xlsx .csv`는 Git이 아닌 Google Drive. 예외: `docs/terms/*.txt` |
| 6 | **projects/ 규칙** | 1단계 폴더까지만, `README.md` 필수, 문서는 `YYMMDD-` 필수, 바이너리·회의 원문 금지 |

보조 규칙:

- 바이너리와 **회의 원문/트랜스크립트**는 Google Drive에서 관리하고, `rclone`으로 `docs/gdrive/`에 내려받아 로컬 참조한다(`gdrive/`는 gitignored).
- `docs/personal/`은 gitignored 로컬 전용. `/create-docs` 스킬이 저장 직전 AskUserQuestion으로 "팀 공유 vs 개인 메모"를 묻고, 개인→팀 전환 시 인터뷰 플로우를 다시 태워 카테고리를 재결정한다. 파일명 규칙은 양쪽이 동일해서 이관 시 리네임이 필요 없다.
- `/create-docs` 스킬(`.claude/skills/create-docs/SKILL.md`)이 카테고리↔폴더↔파일명 패턴 표를 자체 보유하며, 인터뷰로 카테고리를 자동 분류한다. `/update-context` 스킬은 `CLAUDE.md`·`README.md`·`docs/` 구조의 동기화를 점검한다.

## 다른 부분과의 관계

```
docs/guides/          영구 규칙 (상세)  ←→  frontend/CLAUDE.md, backend/services/CLAUDE.md (자동 로드 요약)
        │
docs/features/*.md    기능 명세 (무엇을/왜)
        │  "Canonical Plan"으로 위임
        ▼
.omx/plans/*-plan.md   구현 계획 (어떻게 — 스키마/필드/단계)
        │
        ▼
backend/ · frontend/   실제 코드
        │
        ▼
docs/qa/              검증 결과·핸드오프
```

- **`.omx/`** — [[omx]]에 정리된 대로 `docs/features/`와 양방향으로 물린다. 기능 문서가 "Canonical Plan" 섹션에서 `.omx/plans/`를 정본으로 지목하고, 계획 문서는 헤더에 "원본 문서: `docs/features/...`"로 출처를 밝힌다. `docs/`의 엄격한 구조 가드가 `.omx/`에는 적용되지 않으며(파일명도 `YYYYMMDD-` 8자리로 다름), 이 규칙 회피가 `.omx/`를 `docs/` 바깥 별도 루트에 둔 실질적 이유로 보인다.
- **`.claude/`** — 역할 분담이 명확하다. `docs/guides/`가 **사람과 AI가 읽는 산문 규칙**이라면 `.claude/skills/`는 **실행 가능한 절차**이고, `.claude/memory/`(`people/`, `project/`, `company/`)는 **지속적 팀·회사 지식**이다. 다만 방향은 상호적이어서, `/create-docs`·`/create-meeting-notes`·`/update-context` 스킬이 `docs/` 구조를 직접 다루고 실제 문서 정형성(회의록의 `[KO]`/`[EN]` 구조 등)을 만들어낸다.
- **`backend/` · `frontend/`** — `features/` 문서 헤더의 `관련 서비스:` 필드가 `donation-service`, `photographer-service`, `frontend/app` 등 코드 경로를 직접 가리킨다. `CLAUDE.md`의 "필수 탐색 순서"가 코드 탐색보다 `docs/features/` 확인을 앞세우므로, 문서가 코드의 진입점 역할을 한다.
- **`research/`(저장소 루트)** — 이름이 겹치지만 별개다. 루트 `research/`는 이벤트 리서치 파이프라인(`research-discover`/`enrich`/`adjudicate` 스킬)의 실행 코드·데이터이고, `docs/research/`는 사람이 읽는 시장 분석 산문이다. 혼동 소지가 있는 네이밍이다 — [[research]] 참조.
- **Google Drive** — `docs/`의 명시적 오버플로 대상. 바이너리·회의 원문·정산 자료가 Drive에 있고, `projects/*/README.md`가 Drive 원본 위치를 링크하는 방식으로 두 저장소가 연결된다.

## 관찰 사항

구조 가드가 명문화되어 있는 만큼, 현재 상태와의 불일치가 그대로 드러난다.

1. **`docs/ir/`가 문서화되어 있지 않다.** 전체 파일의 61%(334개)를 차지하면서 `CLAUDE.md`의 `docs/` 구조 트리에도, `/create-docs`의 카테고리 표에도 없다. 동시에 가드 1번(서브디렉터리 — `pitchdeck/assets/` 등 2단계 깊이)과 가드 5번(`.pdf` 10개, 이미지 312개 커밋)을 위반한다. 의도적 예외인지 미갱신인지 저장소에 근거가 없다.
2. **`docs/planning/`에 서브디렉터리가 있다.** `2026-Q2-seanergy-island/`, `2026-Q2-seeding/` 두 폴더는 가드 1번 예외 목록에 없다. 두 폴더 모두 `README.md` + `YYMMDD-` 문서 구조로 `projects/` 패턴을 따르고 있어, `projects/` 도입(2026-07) 이전에 만들어진 선행 사례로 보인다. 폴더명도 `YYMMDD-`가 아닌 `YYYY-Qn-<주제>` 형식이다.
3. **`features/260523-auth-ssot-routes.csv`** — 가드 5번이 금지한 `.csv`가 `features/`에 커밋되어 있다. `docs/` 하위 유일한 비허용 확장자 파일이다.
4. **`CLAUDE.md`에 깨진 링크가 있다.** 288행이 `./docs/guides/face-engine-guide.md`("자체 얼굴 검색 엔진 — AdaFace + pgvector 운영 가이드")를 링크하지만 해당 파일이 존재하지 않는다. `guides/`에서 face 관련 파일은 `face-image-bulk-deletion-guide.md` 하나뿐이다.
5. **`features/`의 `상태:` 값이 표준화되어 있지 않다.** `CLAUDE.md`는 `진행중` → `완료` 전이만 규정하는데 실제로는 `설계`, `기획중`, `운영중`, `구현 완료`, 서술형 복합 상태 등이 쓰인다. 기계적으로 진행 현황을 집계하기 어려운 상태다.
6. **`personal/`과 `gdrive/`는 실질적으로 비어 있다.** gitignored이므로 이 스냅샷에 내용이 없는 것은 당연하지만, 두 폴더의 실제 사용 여부는 로컬 환경에서만 확인 가능하다.
7. **카테고리별 최신성 편차가 크다.** `features/`(~260803), `projects/`(~260802), `qa/`(~260724)는 활발한 반면 `partnerships/`(~260318), `brand/`(~260320), `meetings/`(~260528)는 수개월째 정지 상태다. `meetings/`가 5월 말에 멈춘 것은 회의가 없어서인지 기록 관행이 바뀐 것인지 불분명하다.

## 관련 문서

- [[omx]]
- [[research]]
- [[repo-map]]
- [[project-summary]]
