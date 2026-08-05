# backend — Serverless Lambda 마이크로서비스 군

> 대상 경로: `company-src/oursymbol/backend/` (읽기 전용)
> 실제 코드는 전부 `backend/services/` 아래에 있다. `backend/` 바로 아래에는 `services/` 하나뿐이다.

## 1. 목적 / 역할

스포츠 이벤트 사진 플랫폼 OURSYMBOL의 **전체 서버 사이드**. Flutter 앱과 5개 React 웹앱이 호출하는 모든 API가 여기 있다.

- **Serverless Framework v3** 기반 **AWS Lambda + API Gateway** 구성
- 도메인별로 **19개의 독립 배포 스택**으로 쪼개져 있고, 각 스택이 자체 `serverless.yml`을 가진다
- 런타임은 대부분 **Node.js 18 + TypeScript**(esbuild 번들). 예외 2개 — `face-engine-service`(Python 3.11 Docker), `image-resize-lambda`(Node.js 20)
- 리전은 `ap-northeast-2`(서울) 단일. 스테이지는 `dev` / `prod` 2개 (+ 로컬용 `local`)

### 핵심 구도: 분리 진행 중인 모놀리스

```
services/
├── serverless.yml + src/     ← ourSymbol-api (루트 통합 서비스, "구 모놀리스")
├── <도메인>-service/          ← 여기서 떨어져 나온 독립 서비스들
├── auth-common/              ← 배포되지 않는 공유 인증 라이브러리
├── migrations/               ← 서비스에 속하지 않는 공용 SQL
└── scripts/                  ← 배포 오케스트레이션
```

`services/AGENTS.md`가 명시적으로 규정한다 — **"새 기능은 루트 통합 서비스에 추가하지 않고 독립 서비스로 생성한다."** 루트 `src/`에 남은 것(crew, user, banner, ai, event 앨범, admin, region, appVersion, auth, terms, category, globalRegion, log)은 아직 분리되지 않은 잔여물이다.

단, **auth authorizer만은 루트에 남아 있고 전 서비스가 이를 공유한다** (아래 §4 참조). 즉 루트 서비스는 "레거시"가 아니라 여전히 인증의 중심축이다.

---

## 2. 서비스 목록

### 배포되는 스택 (19개)

| 서비스 | 역할 | 데이터 저장소 | 특이사항 |
|--------|------|--------------|---------|
| **ourSymbol-api** (루트 `src/`) | 소셜/비즈니스 로그인, JWT authorizer, 유저, 크루, 배너, 약관, 지역, 카테고리, 앱 버전, 관리자 | RDS MySQL + DynamoDB | **전 서비스의 authorizer 호스트**. 미분리 기능 집합 |
| **photographer-service** | 작가 관리, 이벤트 참여 신청, 대용량 사진 업로드(presigned URL → SQS → 인덱싱), 삭제요청, UVP | RDS + DynamoDB + S3/R2 | 업로드 파이프라인의 진입점 |
| **session-image-service** | 크루/이벤트 앨범 CRUD, 이미지 업로드·조회, 업로더 관리, **얼굴 검색 진입점** | DynamoDB(7개 테이블) + S3 | 앨범의 `faceEngine` 값으로 검색 엔진 분기 |
| **face-engine-service** | 자체 얼굴 검색 엔진 (Rekognition 대체) | **Aurora PostgreSQL + pgvector**, Cloudflare R2 | 유일한 **Python + Docker(ECR)** 서비스. 10GB RAM |
| **event-service** | 이벤트 도메인(생성·수정·상태축), 앨범 정책, 주최 조직, 카테고리, Slack 연동 | RDS MySQL | 마이그레이션 19개로 최다 — 도메인 재설계가 활발 |
| **commerce-service** | 티켓 판매, 주문, 결제(**Toss Payments**), 래플, 현장 체크인, 패키지, 구매 약관 | RDS + DynamoDB + SQS | 최대 규모(861줄). outbox·DLQ·재고 정합성 등 결제 신뢰성 패턴 |
| **donation-service** | IAP(인앱결제) 검증, 포인트 지갑, 도네이션, 작가 정산/출금, 파트너 계좌 | RDS MySQL | `verifier/` 하위에 스토어 영수증 검증 |
| **office-service** | 운영 백오피스 전용 API (운영자 계정·권한, 작가 심사, 지갑 조정, 이벤트/앨범 관리, 통계, 스튜디오 검수) | RDS + DynamoDB + SQS | 함수 55개로 최다. 다른 서비스 테스트 데이터 준비의 관문 |
| **notification-service** | 푸시 발송(**FCM**), 디바이스 토큰, 알림 카테고리·수신설정, 캠페인·세그먼트, 화이트리스트, 앨범 업로드 알림 | RDS MySQL + SQS 2단 큐 | `firebase-admin` 사용. 10분 주기 alertProcessor |
| **crew-service** | 크루, 크루 앨범, 크루 카테고리 (신규 `Category`+`CrewCategoryMap` 체계) | RDS + DynamoDB + R2 | 루트 `src/crew`에서 분리된 신규 버전 |
| **crew-session-service** | 크루 세션(모임) 생성·참가 신청·출석 체크 | RDS MySQL | |
| **feed-service** | 피드 게시물, 좋아요, 댓글, 신고, **번역**(캐시 테이블) | RDS MySQL | 구 `Moment` v1과 무관한 독립 신규 서비스 |
| **moment-service** | 모먼트(유저×이벤트 단위 사진/티켓 모듈 컨테이너) v2 + v1 레거시 라우트 | RDS + DynamoDB(`MomentPhotos`) | Step Functions(`client-sfn`) 의존 |
| **advertisement-service** | 배너, 메인/이벤트 팝업 광고, 이벤트 타일 광고, 갤러리 배너, 글로벌 광고 | RDS + DynamoDB | |
| **challenge-service** | 챌린지 제출물 수집·검증·리포트, 크루 단위 자동 수집 배치 | RDS + SQS + R2 | Instagram 수집(`apify-client`). 매일 15:00/16:00 UTC 배치 |
| **instagram-service** | 인스타그램 캠페인 CRUD, 제출물, OAuth 토큰 관리, 미디어 조회, 캠페인 리포트 | RDS + SSM | `challenge-service`와 기능이 상당 부분 겹침 (→ questions) |
| **business-service** | 비즈니스 웹앱 로그인/검증 (2개 함수만) | **S3의 `accounts.json`** | 유일하게 `auth-common`을 쓰지 않음. VPC 밖 |
| **kor-triathlon-image-service** | 한국 트라이애슬론 전용 앨범·이미지 조회 (읽기 2개 함수) | DynamoDB | 파트너 전용 읽기 API로 보임 |
| **image-resize-lambda** | CloudFront origin-response 온디맨드 이미지 리사이즈 (Sharp + HEIC 변환) | S3 | Node 20, VPC 밖, 병렬 배포 대상 제외 |

### 배포되지 않는 디렉터리 (3개)

| 디렉터리 | 내용 |
|----------|------|
| `auth-common/` | 공유 인증 라이브러리 + Serverless 플러그인. `workspace:*`로 각 서비스가 의존 |
| `migrations/` | 특정 서비스에 속하지 않는 공용 SQL 11개 (유저 차단, 약관, 리프레시 토큰, 글로벌화 등) |
| `scripts/` | `deploy-parallel.js`(병렬 배포), 일회성 데이터 이관 스크립트 |

---

## 3. 공통 패턴

모든 TypeScript 서비스가 **동일한 골격**을 복제한다. 새 서비스를 만들 때 기존 `serverless.yml`을 복사해 시작하는 것이 사실상의 관행으로 보인다.

### 3.1 `serverless.yml` 공통 블록

```yaml
plugins:
  - ../auth-common/serverless-plugin.js   # 인증 SSOT (아래 §4)
  - serverless-esbuild                     # TS 번들 (bundle, sourcemap, target node18, packager pnpm)
  - serverless-prune-plugin                # 구버전 Lambda 정리: local 2 / dev 3 / prod 10

custom:
  database:  { ourSymbol: { local/dev/prod: ... } }   # 스테이지별 접속 정보
  dynamoDB:  { <테이블>: { tableName: { local/dev/prod: ... } } }
  allowedOrigins: { local/dev/prod: [...] }            # CORS 화이트리스트
```

- **스테이지 분기는 전부 `${self:custom.X.${self:provider.stage}}` 패턴**으로 처리한다. 별도 config 파일이나 SSM 계층은 (일부 서비스 제외) 쓰지 않는다.
- `dev`와 `prod`가 **같은 값을 가리키는 항목이 다수** 있다 (예: 이미지 버킷 다수가 dev/prod 모두 `*-dev` 버킷). 의도인지 미정리인지 불명 (→ questions).
- 대부분의 서비스가 **VPC(고정 보안그룹/서브넷 ID)에 붙는다**. RDS 접근 때문. 예외는 `business-service`, `image-resize-lambda`.

### 3.2 소스 레이아웃

```
<service>/src/
├── handler.ts        # Lambda 진입점 (또는 도메인별 handlers/ 디렉터리)
├── common/db.ts      # mysql2 커넥션
├── model/            # 테이블 접근 계층
├── service/          # 비즈니스 로직
└── utils.ts          # 응답 포맷 등
```

DB 접근은 대부분 **`mysql2` 직접 쿼리**다. ORM은 쓰지 않는다.

### 3.3 데이터 저장소 3분할

| 저장소 | 담는 것 |
|--------|--------|
| **RDS MySQL** (`OurSymbol` DB) | 관계형 도메인 전부 — User, Event, Crew, Order, Wallet, Feed, Photographer … **여러 서비스가 같은 DB·같은 테이블을 공유**한다 (예: `Event` 테이블을 event-service와 commerce-service가 공유) |
| **DynamoDB** | 사진 파이프라인 전용 — `Albums`, `SessionImages`, `ImageProcessingJobs`, `Uploaders`, `AlbumUploaderMapping`(deprecated), `RecognizedPhotoCounts`, `UserHistory`, `MomentPhotos` |
| **Aurora PostgreSQL + pgvector** | 얼굴 임베딩 벡터 (face-engine-service 전용) |

> 서비스 경계가 **DB 단위로 나뉘어 있지 않다.** 마이크로서비스지만 공유 DB 패턴이므로, 스키마 변경은 서비스 간 배포 순서 조율이 필요하다. `event-service/migrations/README.md`가 실제로 "commerce-service와 Event 테이블 공유 중이므로 배포 일정 조율" 체크리스트를 요구한다.

### 3.4 마이그레이션 관리

- 각 서비스가 **자체 `migrations/` 디렉터리에 번호 붙은 SQL 파일**을 둔다 (`001_...sql`, `002_...sql`). 서비스 무관 공용 SQL은 최상위 `migrations/`에 있다.
- **자동 실행 러너가 없다.** `package.json`에 migrate 스크립트가 없고, `schema_migrations` 같은 적용 이력 테이블도 없다. `mysql` 클라이언트로 **사람이 직접 `source` 하는 방식**이다.
- 대신 `event-service/migrations/README.md`처럼 **가이드 문서로 절차를 통제**한다 — 백업 → DEV 검증 → 영향 서비스 조율 → 프로덕션 → 검증 체크리스트 → 롤백 스크립트.
- 명명 규칙이 서비스마다 갈린다: 대부분 `NNN_설명.sql`, `commerce-service`만 `설명_YYYYMMDD.sql` 형식.
- `prod_global_all.sql`이 여러 서비스에 중복 존재 — 글로벌화 작업 때 한 번에 돌린 묶음 스크립트로 보인다.

### 3.5 비동기 처리 — SQS 중심

동기 HTTP 외의 모든 무거운 작업은 SQS를 탄다.

| 큐 | 발행 → 소비 |
|----|-----------|
| `SessionImageProcessingQueue` | photographer/session-image/crew/office → 이미지 인덱싱 워커 |
| `FaceEngineProcessingQueue` | crew-service → face-engine `processImage` (DLQ, 최대 3회 재시도) |
| `NotificationQueue` / `SendQueue` | 각 서비스 → notification-service 2단 발송 파이프라인 |
| `CommerceOutboxQueue` | commerce-service 내부 outbox → 후속 처리(모먼트 티켓 모듈 등) |
| `CollectBatchQueue` | challenge-service 배치 디스패처 → 수집 워커 |

### 3.6 스케줄 배치

| 서비스 | 스케줄 | 함수 |
|--------|--------|------|
| commerce-service | `rate(1 minute)` / `rate(1 hour)` / `cron(0 3 * * ? *)` | 락 만료, 재고 정합, 일일 정산성 작업 |
| notification-service | `rate(10 minutes)` | alertProcessor |
| challenge-service | `cron(0 15 * * ? *)`, `cron(0 16 * * ? *)` | 크루 자동수집 디스패치, 통계 갱신 (dev는 비활성) |
| instagram-service | `cron(0 3 * * ? *)`, `cron(0 1 * * ? *)` | 토큰 갱신, 일일 리프레시 |

---

## 4. 인증 — `auth-common`

백엔드에서 가장 정교하게 설계된 부분이다. **"인증 정책의 SSOT는 각 서비스 `serverless.yml`의 `events.http.auth`"** 라는 단일 원칙 위에 서 있다.

### 구조

```
serverless.yml의 auth.type 선언          ← 사람이 쓰는 유일한 곳 (SSOT)
   ↓ auth-common/serverless-plugin.js (RouteAuthSsotPlugin, package/deploy 시 실행)
   ├─ API Gateway authorizer 설정 자동 생성
   ├─ route-auth-policy.json          (런타임 정책 파일, 자동 생성 — 수동 편집 금지)
   └─ route-auth-audit-catalog.json   (감사 카탈로그)
   ↓
런타임: auth-common/index.js
   requireAuth / requireOwner / requireScope / requireCrewManager / enforceGatewayAuthPolicy
```

### auth 타입

| type | 의미 |
|------|------|
| `public` | 인증 없이 호출 |
| `auth` | 로그인 사용자 |
| `owner` | JWT의 `userId`가 작업 대상과 일치해야 함 |
| `role` / `admin` | 역할·관리자 권한 검사 |
| `crewManager` | 크루 매니저 권한 (크루 멤버십 조회 후 판정) |
| `service` | 서버 간 호출 전용 신뢰 경계 — 앱/브라우저에서 호출 금지 |

### 중요한 사실들

- **authorizer Lambda는 루트 서비스에만 있다.** 각 독립 서비스는 `arn:...:function:ourSymbol-api-${stage}-authAuthorizer`를 외부 authorizer로 참조한다. → **루트 서비스 배포가 전 서비스 인증에 영향을 준다.**
- `auth-common`을 쓰는 서비스는 **19개 중 16개**. 빠진 것은 `business-service`(자체 로그인), `face-engine-service`(API Key), `image-resize-lambda`(CloudFront 전용).
- 레거시 경로(`legacy: allow`, `legacyUserId`, `legacyApiKeys.ts`)가 타입에 남아 있다. 구버전 앱 호환용으로 보이며, 신규 라우트는 `private: true`/`x-api-key` 사용이 **금지**되어 있다.
- 플러그인에 `assertNoManualAuth()`가 있어, `serverless.yml`에서 수동으로 authorizer를 지정하면 배포가 막힌다.

---

## 5. 사진 파이프라인 (도메인 핵심)

플랫폼의 본질적 가치가 여기 있다 — **"내 얼굴이 찍힌 사진을 찾아준다."**

```
① 작가가 presigned URL 요청     → photographer-service / session-image-service
② 클라이언트가 S3(또는 R2)에 직접 업로드 (EXIF 함께 수집 가능)
③ upload-complete 알림          → DynamoDB에 초기 메타 기록, Job 상태 전이
④ SQS 발행
⑤ 워커 Lambda가 인덱싱
      ├─ [기존] AWS Rekognition IndexFaces → Rekognition Collection
      └─ [신규] face-engine: RetinaFace 감지 → AdaFace 512차원 벡터 → pgvector
⑥ Job 상태 COMPLETED

[검색] 유저가 셀피 업로드 → session-image-service가 앨범의 faceEngine 값 확인
      ├─ 없음        → Rekognition SearchFacesByImage
      └─ "pgvector"  → face-engine searchFace Lambda 직접 invoke (코사인 유사도 0.80)
```

### 얼굴 엔진 이원화

DynamoDB `Albums` 테이블의 **`faceEngine` 필드 하나로 앨범별 엔진이 갈린다.**

| `faceEngine` | 엔진 | 이미지 저장 | 벡터/컬렉션 |
|--------------|------|-----------|------------|
| `"pgvector"` | 자체 AdaFace 엔진 | Cloudflare R2 | Aurora pgvector |
| 없음 (기존 앨범) | AWS Rekognition | AWS S3 | Rekognition Collection |

- 크루 신규 앨범은 자동으로 `pgvector`, 이벤트 앨범과 기존 앨범은 Rekognition 유지
- 롤백은 crew-service 환경변수 변경만으로 즉시 가능하도록 설계됨
- 자체 엔진 도입 동기는 **비용**으로 보인다 — R2는 egress 무료, Aurora Serverless v2는 0.5~4 ACU 자동 스케일
- 리사이즈는 3벌 생성: `original`(원본) / `detail`(2048px q85) / `thumb`(400px q75)

> 저장소가 **S3와 Cloudflare R2로 이원화**되어 있다는 점이 중요하다. 신규 경로(face-engine, crew-service, photographer-service, challenge-service)는 R2, 기존 경로는 S3다.

---

## 6. 배포

### 도구는 Serverless Framework v3 하나뿐

`AGENTS.md`가 못박는다 — **AWS CLI/CDK/SAM 직접 사용 금지**, `aws lambda update-function-code` 류 금지.

```bash
# 개별 서비스 (반드시 해당 디렉터리에서 — 루트에서 하면 통합 서비스가 배포됨)
cd backend/services/<서비스>
pnpm exec serverless deploy --stage dev|prod

# 빌드 검증 (배포 없이)
pnpm exec serverless package --stage dev

# 전체 dev 병렬 배포 (기본 병렬도 5)
cd backend/services && pnpm deploy:dev:parallel

# prod 병렬 배포 — 이 형식만 허용
node scripts/deploy-parallel.js --stage prod --confirm-prod -j 5
```

### 배포 규칙

| 규칙 | 이유 |
|------|------|
| **같은 서비스 dev/prod 병렬 배포 금지** | TS 컴파일이 같은 `.build` 디렉터리를 공유해 충돌 |
| 다른 서비스 간 병렬은 OK | 디렉터리가 분리됨 |
| **prod 배포는 사용자 승인 필수** | 전역 규칙 |
| 검증 기준은 `serverless package` | repo-wide `tsc --noEmit`은 서비스 간 타입 부채가 섞여 있어 1차 기준으로 쓰지 않음 |

`scripts/deploy-parallel.js`의 대상은 **16개**이며 로그는 `.deploy-logs/<stage>-<timestamp>/<service>.log`에 남는다. 실패 서비스가 있으면 exit code 1.

---

## 7. 다른 부분과의 관계

### frontend → backend

루트 `CLAUDE.md`의 크로스 의존성 표 기준:

| Frontend | 호출 서비스 |
|----------|------------|
| **app** (Flutter) | ourSymbol-api, photographer, event, session-image, donation, feed, crew-session |
| **studio** (작가용) | photographer, session-image, donation |
| **office** (백오피스) | office, event, photographer, advertisement |
| **event** | event, commerce |
| **business** | event (리포트) — 로그인은 business-service |
| **checkin** | commerce (추정, `VITE_COMMERCE_API_URL`) |
| together / landing / universalLink | 백엔드 의존 거의 없음 |

CORS `allowedOrigins`가 각 `serverless.yml`에 스테이지별로 하드코딩되어 있어, **프론트 도메인/로컬 포트가 바뀌면 백엔드 재배포가 필요**하다. 로컬 포트 번호(5173, 8010, 8020, 8050, 8060)가 프론트 프로젝트와 1:1 대응한다.

### research → backend

`research/` 파이프라인은 **`event-service`의 REST API를 소비하는 외부 클라이언트**다. LLM이 DB나 서비스를 직접 만지는 경로는 없고, Python 드라이버가 event-service API만 호출한다. `event-service/migrations/014_add_event_research_agent.sql`이 그 연동을 위한 스키마 추가로 보인다. → [[research]]

### .claude → backend

`.claude/skills/`의 여러 운영 스킬이 backend API·DB를 직접 호출한다.

| 스킬 | 접점 |
|------|------|
| `/push-notification` | handleId 조회 → SQS → notification-service |
| `/create-event`, `/backfill-event` | event-service API |
| `/manage-business-account` | business-service가 읽는 S3 `accounts.json` CRUD |
| `/update-point-settlement`, `/analyze-revenue` | donation-service 도메인 테이블 (RDS 읽기) |
| `/create-brand-photographer` | R2 업로드 → 관리자 API로 User+Photographer 생성 |
| `/sync-instagram-post` | `SocialPost` → `InstagramPost` (challenge/instagram-service 도메인) |

**DB Read-Only 규칙**(전역)에 따라 이 스킬들은 `SELECT`만 하고, 변경 SQL은 파일로 생성만 하고 실행은 사람이 한다.

### docs → backend

- `backend/services/CLAUDE.md` — `backend/services/` 하위 작업 시 자동 로드되는 핵심 요약
- `backend/services/AGENTS.md` — 배포 상세 가이드 (CLAUDE.md의 상세 버전)
- `docs/features/` — 기능 구현의 입력(spec). 백엔드 변경 전 관련 문서 확인이 필수 절차

---

## 8. 규모 감각

| 항목 | 수치 |
|------|------|
| `backend/services/` 총 파일 수 | 약 560개 |
| 배포 스택 | 19개 |
| `serverless.yml` 총 라인 수 | 약 9,573줄 |
| 최대 `serverless.yml` | photographer-service (871줄) |
| 최다 함수 서비스 | office-service (55개) |
| 최다 마이그레이션 | event-service (19개) |
| 최소 서비스 | business-service (함수 2개, 77줄) |

---

## 9. 읽을 때 주의할 점

- **서비스 이름이 곧 경계가 아니다.** `session-image-service`가 이벤트 앨범도 다루고, `office-service`가 거의 모든 도메인의 쓰기 API를 갖고 있다. `photographerId === userId`처럼 도메인 상의 암묵적 1:1 매핑도 있다.
- **레거시가 여러 겹으로 공존한다.** 카테고리(`CrewCategory` → `Category`+`CrewCategoryMap`), 지역(`Region` → `GlobalRegion`), 모먼트(v1 → v2), 얼굴 엔진(Rekognition → pgvector), 크루(루트 `src/crew` → `crew-service`). 어느 쪽이 현행인지는 루트 `CLAUDE.md`의 "핵심 도메인 지식" 절이 SSOT다.
- **README를 그대로 믿으면 안 된다.** 일부는 Serverless 공식 템플릿 보일러플레이트가 남아 있고, `event-service/README.md`는 내용 자체가 다른 서비스 것이다 (→ questions).
