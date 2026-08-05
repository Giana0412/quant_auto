# Oursymbol 프로젝트 개요

## 시스템 요약
Oursymbol은 스포츠 이벤트 사진 플랫폼으로, AI 기술을 활용하여 작가와 참가자를 연결하는 서비스입니다. AWS Lambda 기반의 서버리스 백엔드와 Flutter/React 기반의 웹/앱 프론트엔드로 구성되어 있습니다.

## 주요 기술 스택
- **Frontend**: Flutter (모바일), React + Vite + TypeScript (웹 콘솔 및 서비스)
- **Backend**: Node.js, TypeScript, Serverless Framework
- **Infrastructure**: AWS Lambda, API Gateway, DynamoDB, RDS (MySQL), S3, Cloudflare R2
- **기타**: Vercel (Frontend 배포), AI 기반 업무 체계 (Claude Code 및 스킬)

## 주요 컴포넌트
1. **Frontend**:
    - `app/`: Flutter 기반 모바일 앱 (iOS/Android)
    - 웹 서비스: 이벤트/결제(`event/`), 비즈니스 분석(`business/`), 관리자 도구(`office/`), 작가 도구(`studio/`), 캠페인 플랫폼(`together/`)
2. **Backend**:
    - `services/`: Serverless Framework로 관리되는 마이크로서비스들 (이벤트, 이미지, 작가, 결제, 광고 등)
3. **Docs/Research**: 프로젝트 문서, 전략 기획, 리서치 자료 및 운영 스크립트

## 개발 환경 및 도구
- **개발 환경**: pnpm workspace 기반 모노레포
- **AI 업무 체계**: Claude Code 기반 스킬 자동화 (반복 업무 처리, 문서 생성, 분석 등)
- **문서화/관리**: 본 저장소는 Obsidian Vault로 구성되어 지식 문서화 관리 수행
- **배포**: Vercel(Frontend), AWS(Backend)
