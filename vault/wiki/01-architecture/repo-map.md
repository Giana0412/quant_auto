---
created: 2026-08-05
updated: 2026-08-12
---

# 저장소 구조 (Repo Map)

## 최상위 디렉터리
- `.claudian/`: Claudian AI 에이전트 설정
- `.obsidian/`: Obsidian Vault 구성 및 플러그인 설정
- `company-src/oursymbol/`: 핵심 코드베이스 (Read-only)
- `vault/`: 지식 및 아키텍처 문서화 공간

## `company-src/oursymbol/` 구조
```
oursymbol/
├── backend/          # Node.js 마이크로서비스 (Serverless Framework)
├── frontend/         # Flutter 앱 및 React 웹 서비스들
├── scripts/          # 운영 유틸리티 스크립트
├── docs/             # 프로젝트 문서 (PRD, 설계, 가이드 등)
├── research/         # 시장 분석 및 연구 자료
├── .claude/          # AI 업무 체계 스킬 및 메모리
└── .omx/             # 계획/전략 문서
```

## 주요 진입점 및 실행 명령어
- **개발 서버 실행**: `pnpm dev:<project_name>` (예: `pnpm dev:event`)
- **백엔드 배포**: `serverless deploy --stage <stage>` (루트: `backend/services/`)
- **의존성 설치**: `pnpm install` (루트)

## 기타 참고
- **민감 정보**: .env 파일은 Git에 관리되지 않으며, Git 내부에 인증 토큰, 비밀키, 환경 설정 파일 등을 직접 저장하지 않도록 주의. (예시 파일 `.env.example` 만 존재)

---

## 모듈 문서 (`vault/wiki/02-modules/`)

위 코드베이스를 모듈별로 풀어 쓴 문서들이다.

| 모듈 | 문서 |
|---|---|
| `backend/` | [[backend]] |
| `frontend/` | [[frontend]] |
| `docs/` | [[docs]] |
| `research/` | [[research]] |
| `.omx/` | [[omx]] |
| `.claude/` | [[dot-claude]] |

## 이 vault 자체를 다루는 문서

| | |
|---|---|
| 왜 만들었나 | [[vault-rationale]] |
| 전체 설계 | [[oao-wiki-설계문서]] · [[oao-wiki-설계문서-쉬운설명]] |
| 서버·폴더·링크·태그 구조 | [[전체-구조도]] |
| 자동화 동작 | [[자동화-동작구조]] |
| 미해결 질문 축적소 | [[questions]] |
| 작업 이력 (append-only) | [[session-log]] |
| 규칙 위반 자동 점검 (주 1회) | [[lint-report]] |

## 목차 (자동 생성)

| | |
|---|---|
| 회의별 3종 문서 | [[회의]] |
| vault 전체 문서 지도 | [[문서지도]] |
| raw/slack 폴더 안내 | [[raw-slack-안내]] |
| 회의록 3종 형식 규격 | [[템플릿-가이드]] |

## 규칙 (schema — 사람이 정한다)

| | |
|---|---|
| 어느 폴더에 둘지 | [[폴더-규칙]] |
| 문서 맨 위 메타데이터 | [[프론트매터-규격]] |
| 문서끼리 잇는 법 · 태그 | [[링크-규칙]] |
| 규칙이 지켜지는지 점검 | [[lint-규칙]] |
| 질문에 근거로 답하는 규약 | [[query-규칙]] |
| Hermes(사서)가 언제 무엇을 하는가 | [[에이전트-역할]] |
| 회의 3종 문서 형식 | [[템플릿-가이드]] |
