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
