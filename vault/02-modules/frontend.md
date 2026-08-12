---
created: 2026-08-05
updated: 2026-08-05
---

# frontend — 모바일 앱 + 웹 서비스 묶음

## 목적 / 역할

`frontend/`는 아워심볼(스포츠 이벤트 사진 플랫폼)의 **모든 클라이언트 코드**를 담는 디렉터리다. 단일 앱이 아니라 **Flutter 모바일 앱 1개 + React 웹 서비스 7개 + 정적 HTML 1개 + 공유 패키지 1개**로 구성된 다중 프로덕트 묶음이다.

구성을 가르는 축은 **누구를 위한 화면인가**다.

| 대상 | 프로젝트 |
|------|----------|
| 일반 유저(참가자) | `app`(모바일), `event`, `together`, `landing` |
| 사진작가 | `studio` |
| 내부 운영자 | `office` |
| 외부 고객사(주최사·광고주) | `business`, `checkin` |
| 인프라성 | `universalLink`(딥링크 리다이렉트), `shared`(공유 코드) |

React 프로젝트 8개(`shared` 포함)는 **pnpm workspace 모노레포**로 묶여 있고, Flutter 앱만 그 바깥의 독립 프로젝트다.

## 앱별 요약

| 앱 | 역할 | 주요 기술스택 | 라우팅 | 배포 | dev 포트 |
|----|------|--------------|--------|------|---------|
| `app` | 참가자용 모바일 앱 (사진 검색/구매, 크루, 모먼트, 챌린지) | Flutter 3, Provider, Dio+Retrofit, Firebase, Hive | go_router | App Store / Play Store | — |
| `event` | 마라톤·스포츠 이벤트 **티켓 구매** 플랫폼 | React 19 + Vite, Tailwind 3, TanStack Query, TossPayments SDK | react-router-dom | Vercel (`event.o-sym.com`) | 8010 |
| `business` | 고객사 전용 **리포트 콘솔** (운영 성과 / 광고 성과) | React 19 + Vite, Tailwind 4, TanStack Router+Query, Recharts, Zustand | TanStack Router | Vercel | 8020 |
| `landing` | 서비스 소개 랜딩 + 작가 프로필 공유 페이지 | React 19 + Vite, Tailwind 3 (의존성 최소) | react-router-dom | Vercel | 8030 |
| `together` | **후원 캠페인** 플랫폼 (도전자 응원/후원) | React 19 + Vite, Tailwind 3, Firebase Firestore | react-router-dom | Vercel (`together.o-sym.com`) | 8040 |
| `studio` | **작가 관리 콘솔** (앨범/이미지 업로드, 정산, 크루) | React 19 + Vite, Tailwind 4, TanStack Router+Query, Zustand, exifr/heic2any | TanStack Router | Vercel | 8050 |
| `office` | **내부 운영 콘솔** (이벤트/작가/광고/심사/정산/푸시) | React 19 + Vite, Tailwind 4, TanStack Router+Query+Table, Zustand, ffmpeg.wasm, S3 SDK | TanStack Router | Vercel | 8060 |
| `checkin` | 현장 **QR 체크인** 도구 (참가자 명단 확인) | React 19 + Vite, Tailwind 4, TanStack Router+Query, qr-scanner | TanStack Router | Vercel | 8070 |
| `universalLink` | `app.o-sym.com` 앱 딥링크 리다이렉트 | 정적 HTML (빌드 없음) | — | AWS S3 (`app-o-sym-com-redirect`) | — |
| `shared` | 공유 타입/유틸/Firebase/i18n 패키지 | TypeScript 라이브러리 (`@oursymbol/shared`) | — | 배포 대상 아님 | — |

규모 참고(파일 수): `app` 829, `event` 142, `studio` 112, `business` 76, `office` 71, `together` 71, `checkin` 40, `shared` 25, `landing` 19, `universalLink` 4. 앱 하나가 나머지 전부보다 크다.

### 각 앱 보충

- **`app` (Flutter)** — `lib/` 아래가 `api/`(도메인별 20여 개: `event`, `commerce`, `donation`, `crews`, `moment`, `feed`, `sessionImage`, `photographer`, `advertisement`, `notification` …), `screens/`(home, event, crew, lounge, challenge, mypage), `services/`(FCM, IAP, 얼굴 검색용 이미지 업로드, 애널리틱스, WebView 인증 브리지 등), `widgets/`, `providers/`로 나뉜다. 상태관리는 Provider + ChangeNotifier, DI는 get_it, 로컬 저장은 Hive + secure_storage. 소셜 로그인(Google/Apple/Kakao)과 Firebase(Crashlytics, Firestore, Remote Config)를 쓴다. `pubspec.yaml` 기준 버전 `4.8.1+393`.
- **`event`** — 이벤트 상세 + 티켓 결제. 결제는 TossPayments. 빌드 시 `scripts/generate-event-html.js`가 특정 이벤트용 정적 HTML(예: `/event/1`)을 생성하고, 그 외 이벤트는 `api/og/event.js`가 OG 메타를 동적 생성한다. i18n(ko/ja/en) 적용.
- **`business`** — 리포트 데이터를 API가 아니라 **커밋된 정적 JSON**(`public/data/event-{id}/report.json`)에서 읽는 구조. 이 JSON은 `.claude/skills/`의 `/generate-organizer-report`·`/generate-advertisement-report` 스킬이 BigQuery+RDS를 조회해 생성한다. 인스타그램 캠페인 분석 화면(`pages/instagram/`, `config/instagramApi.ts`)도 함께 들어 있다.
- **`together`** — 백엔드 서비스를 쓰지 않는 유일한 웹 서비스. 후원 내역은 **Google Sheets**, 응원 메시지는 **Firebase Firestore**에서 가져온다. 15개 은행 앱 딥링크로 계좌 이체를 유도하는 모바일 특화 UI.
- **`office`** — 라우트가 곧 운영 업무 목록이다: `events`, `albums`(사진 심사), `studio-reviews`, `users`, `crews`, `donation`, `settlement`, `advertisements`, `operators`, `push`. R2 업로드·영상 압축(ffmpeg.wasm)을 클라이언트에서 처리한다.
- **`studio`** — `features/` 단위로 구성(`upload`, `events`, `crews`, `donation`, `payout`, `activity`, `dashboard`, `auth`). 업로드 경로에서 EXIF 파싱(exifr)과 HEIC 변환(heic2any)을 브라우저에서 수행한다.
- **`landing`** — 의존성이 4개뿐인 가장 가벼운 프로젝트. `/photographer/@:handleId` 요청은 Vercel Function `api/og/photographer.ts`로 리라이트되어 작가별 OG 메타를 서빙한다.
- **`checkin`** — 단일 기능 앱. `features/checkin/` 하나에 QR 스캔 탭 / 명단 탭 / 체크인 결과 시트가 모두 들어 있다.

## 공통 기반

### pnpm workspace + catalog

루트 `pnpm-workspace.yaml`이 프론트 8개 패키지와 백엔드 서비스를 한 워크스페이스로 묶고, **catalog**로 핵심 의존성 버전을 중앙 고정한다.

| catalog | 고정 대상 |
|---------|----------|
| `react` | react / react-dom 19, 타입 |
| `ui` | radix slot, cva, clsx, lucide-react, tailwind-merge |
| `routing-state` | @tanstack/react-query, react-router-dom, react-helmet-async |
| `firebase` | firebase |
| `frontend-build` | vite, typescript, @vitejs/plugin-react |

명령은 루트에서 `pnpm dev:<app>` / `pnpm build:<app>` / `pnpm build:all` 형태로 통일되어 있고, 환경변수는 `pnpm env:pull`로 Vercel에서 내려받는다. Node 22 이상, pnpm 10 이상.

### `shared/` — 공유 패키지의 실제 범위

`@oursymbol/shared`는 subpath export로 노출된다.

| export | 내용 |
|--------|------|
| `./types` | RDS / DynamoDB / 공통 도메인 모델 타입 (`types/models/{rds,dynamo,common}`) |
| `./firebase` | Firebase 초기화 설정 |
| `./i18n` | i18next 설정 |
| `./locales/{ko,ja,en}.json` | 번역 리소스 3개 언어 |
| `./config/feature-flags` | 국가별 기능 on/off |
| `./utils` | `cn`, 날짜, 검증, 유저 설정 |
| `./ui` | (현재 `cn` 재export만 있고 컴포넌트는 없음) |
| `./tailwind-config` | 공용 Tailwind 프리셋 |

의존하는 곳은 `event`, `office`, `studio`, `together` 4개다. `business`, `checkin`, `landing`은 shared를 쓰지 않는다.

`config/feature-flags.ts`는 **국가 코드별로 기능을 켜고 끄는 구조**(`KR` / `JP` / `WW`)이고, 주석에 "source of truth는 서버 API `GET /service-config`이며 이 파일은 서버 실패 시 fallback"이라고 명시돼 있다. KR만 CREW·POINT·DONATION·CHALLENGE가 켜져 있고 JP/WW는 EVENT/PHOTO/MOMENT/FEED만 열려 있다 — 일본·글로벌 확장이 진행 중이되 포인트/후원 경제는 아직 한국 전용이라는 뜻으로 읽힌다.

### 규칙 (`frontend/CLAUDE.md`)

- Flutter: Provider 중심, `setState` 최소화, 파일명 snake_case, 하드코딩 색상/사이즈 금지.
- React: `any` 금지, 하드코딩 값 금지, 브라우저 노출 환경변수는 `VITE_` prefix 필수, Vercel 배포 시 `--scope o-sym`.
- **라우팅이 이원화되어 있다.** `office`/`studio`/`business`/`checkin`은 TanStack Router, `event`/`landing`/`together`는 react-router-dom. CLAUDE.md에 "향후 TanStack Router로 통일 예정"이라고 적혀 있다.
- 린터도 이원화: TanStack Router 계열 4개는 **Biome**, 나머지는 **ESLint**.
- `photographerId === userId` (1:1 매핑) 는 프론트 전역에서 전제되는 도메인 규칙.

## 다른 부분과의 관계

### backend 호출 관계

루트 `CLAUDE.md`가 명시한 매핑에 각 앱의 `services/`·env 변수명으로 확인한 내용을 합치면 다음과 같다.

| Frontend | 호출하는 backend 서비스 | 확인 근거 |
|----------|------------------------|----------|
| `app` | 메인 서비스, photographer, event, session-image, donation, feed, crew-session, commerce, moment, advertisement, notification | `lib/api/` 하위 도메인 디렉터리 구성 |
| `studio` | photographer-service, event-service, donation-service, session-image-service | `services/*.ts` 파일명 + `VITE_*_API_URL` 변수명 |
| `office` | office-service, event-service, photographer-service, advertisement-service, donation-service, notification-service, crew-service, session-image-service | `VITE_*_API_URL` 변수 7종 |
| `event` | event-service, commerce-service, user API | Vercel 프록시 라우트 `/api/{event,commerce,user,challenge}` |
| `business` | event-service (리포트용) — 다만 주 데이터는 커밋된 정적 JSON | README + `config/reportConfig.ts` |
| `checkin` | commerce API (`VITE_COMMERCE_API_URL`) 등 | `.env.example` 변수명 |
| `together` | 없음 (Google Sheets API + Firestore 직접) | package.json에 axios 없음, firebase만 |
| `landing` | 작가 프로필 조회 API (OG 생성용) | `api/og/photographer.ts`, `VITE_PHOTOGRAPHER_API_URL` |
| `universalLink` | 없음 | 정적 HTML |

### Vercel Functions 프록시 레이어

`event`, `together`, `landing` 세 곳은 정적 SPA만이 아니라 **`api/*.js` Vercel Serverless Function**을 함께 배포한다.

```
브라우저 → Vercel Function (api/*.js) → 백엔드 서비스 / Google Sheets
             ├ API 키를 서버 측에 보관 (클라이언트 미노출)
             ├ Origin 검증 (api/utils/security.js)
             └ 응답 재포장
```

`frontend/CLAUDE.md`가 특히 강조하는 함정: **프록시가 백엔드 4xx/5xx를 `{ error, message, details: <백엔드 원본 body> }`로 재포장**하기 때문에, 백엔드 코드만 보고 에러 구조를 판단하면 틀린다. 프론트에서는 `error.response.data.details.error`로 접근해야 한다. 로컬 dev도 vite 프록시가 배포된 Vercel을 향하므로 응답 구조는 환경 무관하게 동일하다.

`together`의 프록시는 보안보다 **개인정보 마스킹** 목적이 크다 — `/api/donations`는 후원자 이름을 마스킹해서, `/api/donations-full`은 전체 이름으로 반환한다.

### `.claude/` 와의 관계

단순 참조가 아니라 **빌드 입력을 생성하는 관계**가 하나 있다. `business/`의 리포트는 `.claude/skills/generate-organizer-report`·`generate-advertisement-report`가 BigQuery+RDS에서 뽑아 만든 `report.json`을 커밋한 뒤 정적 서빙하는 구조다. 즉 `.claude/` 스킬이 `business/public/data/`의 데이터 소스 역할을 한다.

그 외 `/create-event`, `/push-notification`, `/manage-business-account` 등 운영 스킬은 `office`가 UI로 제공하는 기능과 목적이 겹친다(운영자가 화면 대신 CLI로 처리하는 경로).

### `docs/` 와의 관계

`frontend/CLAUDE.md`는 요약이고 상세는 `docs/guides/`에 있다 — `flutter-guide.md`, `react-vite-guide.md`, `vercel-guide.md`, `monorepo-guide.md`, `api-integration-guide.md`, `env-management-guide.md`, `universal-link-guide.md`.

## 관찰 사항

- **workspace에 없는 디렉터리가 등록되어 있다.** `pnpm-workspace.yaml`은 `frontend/push`를 패키지로 선언하지만 해당 디렉터리는 존재하지 않는다. 루트 `package.json`에도 `dev:push`/`build:push` 스크립트는 없다.
- **`checkin`이 상위 문서에 누락돼 있다.** 루트 `CLAUDE.md`의 프로젝트 표·크로스 프로젝트 의존성 표, `frontend/CLAUDE.md`의 React 프로젝트 목록 모두 `checkin`을 언급하지 않는다(`landing`도 크로스 의존성 표에만 있고 React 규칙 목록에는 없다).
- **`event/`에 `netlify.toml`과 `vercel.json`이 공존한다.** 실제 배포는 Vercel이므로 Netlify 설정은 과거 잔재로 보인다.
- Flutter `pubspec.yaml`의 SDK 제약이 `>=2.18.6 <3.0.0`으로 Dart 3 이전에 묶여 있다.
- 잔재로 보이는 파일: `app/archive.zip`(448B), `studio/src/metadata.old.json`(235B).
- `shared/src/ui/index.ts`는 "공유 UI 컴포넌트" 자리이지만 실제로는 `cn` 유틸 재export만 있다. 공용 디자인 시스템은 아직 각 앱의 로컬 `components/ui/`(shadcn 스타일)에 흩어져 있다.
- 환경변수는 **이름만** 확인했고 값은 어떤 것도 문서에 옮기지 않았다. 실제 값은 Vercel 대시보드에서 `pnpm env:pull`로 받는다.

## 관련 문서

- [[repo-map]]
- [[project-summary]]
- [[backend]]
- [[dot-claude]]
- [[docs]]
