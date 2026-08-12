---
created: 2026-08-05
updated: 2026-08-05
---

# .omx — 구현 계획(Plan) 저장소

## 목적 / 역할

`.omx/`는 oursymbol 모노레포 루트에 있는 **AI 에이전트 작업용 계획 문서 보관 디렉터리**다.

기능 명세(`docs/features/`)와 실제 구현 사이의 중간 산출물, 즉 **"이 기능을 어떤 스키마와 어떤 순서로 만들 것인가"를 확정한 canonical plan**을 담는다.

핵심 성격 두 가지:

- **Git 추적 대상이다.** 같은 도트 디렉터리라도 `.omc/`는 `.gitignore`에 `.omc/`, `**/.omc/`로 제외되어 있는 반면, `.omx/`는 제외 규칙이 없고 실제로 `git ls-files`에 잡힌다. 즉 세션 임시 상태가 아니라 **팀이 공유하는 영속 산출물**로 취급된다.
- **기능 문서가 이 디렉터리를 정본으로 참조한다.** `docs/features/260503-challenge-submission-mvp.md`는 "## Canonical Plan — 상세 구현 계획은 `.omx/plans/...`를 따른다"라고 명시하며 구현 상세를 `.omx/`로 위임한다. 즉 `docs/features/`가 "무엇을/왜"라면 `.omx/plans/`는 "어떻게(스키마·필드·인덱스 수준)"를 맡는 계층이다.

## 하위 구조

현재 로컬 스냅샷 기준 디렉터리 전체는 다음 한 갈래뿐이다.

```
.omx/
└── plans/
    └── 20260429-app-campaign-detail-page-review-plan.md
```

| 경로 | 설명 |
|------|------|
| `plans/` | 구현 계획 문서. 파일명 규칙은 `YYYYMMDD-<주제>-plan.md` (8자리 전체 연도) |

### `20260429-app-campaign-detail-page-review-plan.md`

앱 소셜 챌린지(캠페인 상세 페이지) 기능의 **DB 스키마 설계 초안**. 문서 헤더에 작성일·원본 문서 경로·`상태: draft`를 두는 형식이다.

내용 요약 (필드 정의 전문은 옮기지 않음):

- **네이밍 결정** — 푸시/CRM 도메인의 `Campaign`, 인스타 추적 도메인의 `Campaign`과 이름이 충돌하므로 신규 도메인은 `Campaign`을 쓰지 않기로 결정. 내부 루트 엔티티는 `SocialChallenge`, 유저/운영 화면 용어는 "챌린지".
- **엔티티 설계** — `SocialChallenge`(챌린지 본체), `SocialPost`(플랫폼 중립 게시물 원본), `SocialSubmission`(챌린지↔게시물 제출 연결), `UserSocialAccountLink`(유저 SNS 계정 연결), `SocialIngestionLog`(자동 수집 실행 로그), `SocialChallengeManager`(담당 관리자 매핑). 각 엔티티마다 필드 표·ENUM 값 후보·인덱스 초안·설계 의도 비고를 갖춘다.
- **레거시 대체 매핑** — `InstagramCampaign` → `SocialChallenge`, `InstagramCollectLog` → `SocialIngestionLog`, `InstagramPost`가 갖던 챌린지 귀속 책임 → `SocialSubmission`.
- **도입 범위 단계화** — 1차 필수 / 1차 선택 / 2차로 엔티티를 나눠 MVP 경계를 명시.
- **보류 항목** — `slug` 재도입 여부, `instagram-service` 내부 리네이밍만 할지 서비스 경계까지 재정리할지 등 미결 논점을 문서 말미에 남긴다.

문서 성격상 **결정 사항과 그 근거, 그리고 아직 결정하지 않은 것**을 함께 기록하는 설계 의사결정 로그에 가깝다. 순수 스펙 문서가 아니다.

## 다른 부분과의 관계

```
docs/features/*.md          기능 명세 (무엇을/왜)
        │  "Canonical Plan"으로 위임
        ▼
.omx/plans/*-plan.md        구현 계획 (어떻게 — 스키마/필드/단계)
        │  구현 입력
        ▼
backend/services/           실제 코드 + migrations/*.sql
```

- **`docs/features/`** — 양방향 참조 관계다. 계획 문서는 헤더에 "원본 문서: `docs/features/...`"를 적어 출처를 밝히고, 기능 문서는 "Canonical Plan" 섹션에서 `.omx/plans/`를 정본으로 지목한다. `docs/`에는 서브디렉터리 금지·`YYMMDD-` 접두사 같은 엄격한 구조 가드(CLAUDE.md)가 걸려 있는데, `.omx/`는 그 규칙 바깥에 있다 — 파일명도 `YYYYMMDD-`(8자리)로 `docs/`의 `YYMMDD-`(6자리)와 다르다. 이것이 `.omx/`가 `docs/` 하위가 아닌 별도 루트 디렉터리로 존재하는 실질적 이유로 보인다.
- **`backend/`** — 계획의 구현 대상. 이 계획에서 설계한 스키마는 `backend/services/challenge-service/`(및 `migrations/001_create_challenge_submission_tables.sql` 등)로 실체화되어 있고, 충돌 지점으로 지목된 코드는 `backend/services/notification-service/`, `backend/services/instagram-service/`다.
- **`frontend/`** — 직접 참조는 없다. 다만 계획 문서 §9 "앱 화면 매핑"이 앱 UI 섹션(챌린지 정보 / 참여 현황 / 내 참가 현황)과 엔티티를 연결하므로, Flutter 앱(`frontend/app/`) 화면 요구사항이 스키마 설계의 입력으로 반영되어 있다.
- **`.claude/`, `.agents/`** — 역할이 겹치지 않고 보완적이다. `.claude/skills/`·`.agents/skills/`는 **재사용 가능한 절차(워크플로우 정의)**를 담고, `.claude/memory/`는 **지속적 팀/회사 지식**을 담는다. `.omx/plans/`는 그와 달리 **특정 기능 하나에 귀속된 일회성 설계 산출물**이다.
- **`.omc/`** — 이름은 비슷하지만 별개다. `.omc/`는 oh-my-claudecode의 런타임 상태 디렉터리로 `.gitignore` 처리되어 있고, `.omx/`는 커밋되는 문서 디렉터리다. (`.omx`라는 이름 자체의 유래는 저장소 어디에도 설명이 없다 — 아래 질문 참조.)

## 관찰 사항

- 계획 문서 내부의 코드 참조 링크가 **다른 사람의 로컬 머신 절대 경로**(`/Users/<사용자>/Workspace/oursymbol/...`) 형태로 박혀 있다. 저장소를 clone한 다른 환경에서는 링크가 깨진다.
- 계획 문서에 `accessToken` / `refreshToken` 필드 **설계**가 포함되지만, 실제 토큰 값은 문서에 없다(스키마 정의뿐).
- git 로그상 `.omx/` 관련 커밋은 1건("Capture a leaner social challenge schema before implementation")으로, 이 디렉터리 자체가 비교적 최근에 도입된 관행으로 보인다.

## 관련 문서

- [[repo-map]]
- [[project-summary]]
