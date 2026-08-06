# Session Log

Gemini 기반 모듈 문서화 작업 기록입니다. 실행마다 한 줄씩 추가됩니다.

| 시각 | 대상 | 출력 파일 | 상태 | 비고 |
|---|---|---|---|---|
| 2026-08-05 | .omx | vault/02-modules/omx.md | 실패 | gemini CLI 무료 티어 일일 할당량 초과 (429 TerminalQuotaError, gemini-3.5-flash, limit 20 req/day). 파일 생성 안 됨. |
| 2026-08-05 | (전체) | - | 방침 변경 | gemini 할당량 문제로 Claude 서브에이전트(general-purpose)로 전환. 이후 모든 모듈 문서화는 Claude 에이전트가 수행. |
| 2026-08-05 | .omx | vault/02-modules/omx.md | 성공 | Claude 서브에이전트(doc-omx). questions.md에 [omx] 항목 5건 추가. |
| 2026-08-05 | research | vault/02-modules/research.md | 성공 | Claude 서브에이전트(doc-research). questions.md에 [research] 항목 7건 추가. |
| 2026-08-05 | .claude | vault/02-modules/claude.md → dot-claude.md | 성공(파일명 수정) | Claude 서브에이전트(doc-claude). macOS 대소문자 비구분 파일시스템에서 `claude.md`가 `CLAUDE.md`(프로젝트 지침 자동로드 대상)와 동일 파일로 인식되어 하네스가 실제로 이 문서를 지침처럼 불러들이는 사고 발생. `dot-claude.md`로 즉시 rename하고 frontend.md의 [[claude]] 링크를 [[dot-claude]]로 수정. |
| 2026-08-05 | docs | vault/02-modules/docs.md | 성공 | Claude 서브에이전트(doc-docs). |
| 2026-08-05 | frontend | vault/02-modules/frontend.md | 성공 | Claude 서브에이전트(doc-frontend). |
| 2026-08-05 | backend | vault/02-modules/backend.md | 성공 | Claude 서브에이전트(doc-backend). 옵션 A(모듈 문서화) 6개 전부 완료. |
| 2026-08-06 | Slack 연동 | .obsidian/plugins/slack-sync/ | 성공 | obsidian-slack-sync 플러그인 설치. 코드 버그 2건 수정(비공개 채널 조회 안 됨, 스레드 답글 channel 파라미터 오류) + 파일 첨부(files[]) 미지원 문제 수정. `.gitignore`로 토큰 파일 보호. |
| 2026-08-06 | 06-docs 파이프라인 | vault/06-docs/ | 성공 | 원온원 미팅 전사본 1건을 전사본/정리본/결정사항 3종으로 수동 정리 (`260804-상욱현지규형원온원-*.md`). 템플릿은 `_템플릿-가이드.md`에 고정. |
| 2026-08-06 | 자동화 구축 | .automation/, launchd | 성공 | Slack Sync autoSync 켬(1시간 간격). `.automation/process-slack-docs.sh` + launchd(`com.giana.obsidian-slack-docs-sync`, 1시간마다, RunAtLoad)로 vault/05-slack→06-docs 자동 문서화 파이프라인 구성. 첫 실행 검증 완료(신규 원본 없어 정상 스킵). 클라우드 cron(`schedule`/RemoteTrigger)은 로컬 파일 미접근+git 자동 push/pull 미설정으로 부적합 판단, 로컬 launchd로 대체. |
| 2026-08-06 | 캘린더/알림 자동화 (대기) | process-slack-docs.sh STAGE2 | 대기 | 액션아이템→Slack 기한문의→답장파싱→Google Calendar 등록→당일 Slack 알림 로직을 STAGE2로 작성해 스크립트에 추가했으나 `STAGE2_ENABLED=false`로 비활성 상태. 선행조건 대기 중: (1) Google Calendar MCP 연결(`claude.ai/customize/connectors`, 사용자 브라우저 작업 필요 — CLI로 시도했으나 "Incompatible auth server: dynamic client registration 미지원"으로 실패), (2) Slack 앱에 `chat:write`+`im:write` 스코프 추가 및 재설치. 상태 저장은 `.automation/action-items.json`. |
| 2026-08-06 | 캘린더/알림 자동화 (활성화+검증) | process-slack-docs.sh STAGE2 | 성공 | Calendar MCP 연결, Slack 스코프 재발급 완료 확인 후 `STAGE2_ENABLED=true`, 정확한 MCP 도구명(`mcp__claude_ai_Google_Calendar__*`)을 allowedTools에 반영. 라이브 테스트: [A]Slack 기한문의 게시 확인 → [B]사람 답장(채널에 평문 타이핑, 스레드 아님) 최초엔 못 잡는 버그 발견(`conversations.replies`만 확인) → `conversations.history`도 같이 보게 수정 → 재실행해서 정상 파싱+Calendar 이벤트 생성 확인. 보안 이슈: 초기엔 `$SLACK_TOKEN` env var가 Bash(curl:*) 셸 확장 차단에 막혀 헤드리스 에이전트가 토큰을 curl 인자에 직접 타이핑(세션 트랜스크립트에 평문 노출) → `curl -K .automation/.slack-auth.curlrc`(런타임 생성, 매 실행 후 shred 삭제) 방식으로 교체해 해결. 이후 실행에서 종일 일정으로 잘못 생성된 버그 발견(시각 정보 버림) → 스키마에 `due_time` 추가, 기존 이벤트 2건 수동 보정(update_event). |
| 2026-08-06 | Notion 연동 + person-profile 초안 | vault→personal/07-profile | 성공 | Notion MCP 연결(로컬 CLI는 `claude mcp login` 별도 브라우저 인증 필요했음). 자기소개+프로젝트 15건(중복 2건 병합→14건) 가져와 self-intro.md/portfolio.md 생성. GitHub(`gh` CLI, 이미 인증됨) 커밋 이력 등 기존 데이터 기반으로 person-profile.md 초안 작성(인터뷰 대신 근거 기반 추론), 사용자 확인 거쳐 1건 수정(속도>완벽 → 완벽 우선으로 정정). |
| 2026-08-06 | 회사/개인 vault 분리 + 히스토리 정화 | personal/ (신규, 로컬 전용 repo) | 성공 | `vault/07-profile`, `vault/08-imports`(카톡/왓츠앱 수동 임포트용, 신규 생성)를 바깥 vault repo에서 분리해 `personal/`(별도 `git init`, 원격 없음)로 이전 — `company-src/oursymbol`이 바깥 repo와 분리된 것과 동일 패턴. `.gitignore`에 `personal/` 추가. 이미 GitHub(origin, private repo)에 push까지 됐던 과거 커밋이 있어, `git-filter-repo`(brew 설치) + `--force`로 전체 히스토리에서 해당 경로 완전 제거 후 `git push --force`로 원격 히스토리까지 정화. 작업 전 안전용 `git bundle` 백업 생성. 최종 확인: 로컬/원격 모두 해당 경로 히스토리 0건. |
