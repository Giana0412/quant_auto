---
name: promote
description: |
  vault에서 확정된 결정사항·문서를 모노레포(oursymbol) docs/ 로 승격하는 PR을 만든다.
  Keywords: "승격", "승격해줘", "확정됐어", "모노레포에 올려줘", "정식 문서로", "promote"
---

# Promote (확정 문서 승격)

## 목표

vault에 쌓인 "거친 중간 맥락" 중 **확정된 것만** 모노레포 `docs/` 로 올려
git이 SSOT라는 원칙을 지키면서 vault가 메모 무덤이 되지 않게 한다.

> 기획서가 명시한 배드 시나리오 2번: *"vault만 만들고 승격 루틴이 없으면 그냥 메모
> 무덤이 됨."* 이 스킬이 그 방어막이다. — `vault/00-overview/vault-rationale.md`

## 언제 사용하는가?

- "이거 확정됐어, 정식 문서로 올려줘"
- "모노레포에 반영해줘"
- 결정사항이 실제로 시행되어 되돌릴 일이 없어졌을 때

## 승격하지 않는 것

| 대상 | 이유 |
|---|---|
| 회의 전사본·정리본 | 회의 원문은 Git에 두지 않는다 (모노레포 CLAUDE.md 가드 5 주석) |
| 아직 보류·미결인 항목 | 확정된 것만 올린다 |
| 바이너리 | Drive에 두고 링크만 |
| 세일즈 딜 진행 상황 | 계속 바뀌는 맥락 — vault에 남는다 |

**결정사항 문서라도 통째로 옮기지 않는다.** 확정된 내용을 모노레포 문서 형식으로
**다시 쓴다.** vault 원문은 vault에 그대로 남는다.

## 사전 조건

```bash
ls company-src/oursymbol/.git   # 모노레포가 로컬에 clone돼 있어야 함
gh auth status                  # GitHub 인증
```

모노레포는 vault 레포에서 추적하지 않는다(gitignore). 없으면 이 스킬은 쓸 수 없고,
비개발자에게는 **김규형님께 요청하시라고 안내**한다 (결정 #11: 비개발자는 모노레포를 볼 필요 없음).

## AI 수행 절차

### Step 1: 대상 확인

승격할 vault 문서를 특정한다. 보통 `vault/06-docs/03-결정사항/` 아래다.
사용자가 지정하지 않았으면 최근 결정사항을 보여주고 고르게 한다.

문서를 Read해서 **확정 항목과 보류 항목을 분리**한다. 보류는 올리지 않는다.

### Step 2: 카테고리 결정

모노레포 `docs/` 의 어느 폴더인지 정한다. **애매하면 AskUserQuestion으로 확인.**

| 폴더 | 내용 | 파일명 |
|---|---|---|
| `features/` | 기능 명세, PRD, API·기술 설계 | `YYMMDD-` 필수 |
| `guides/` | 영구 규칙·절차 (코딩 스타일, 배포 절차) | **날짜 접두사 금지** |
| `projects/<프로젝트명>/` | 프로젝트 단위 아카이브 | `YYMMDD-` 필수 (README 제외) |
| `meetings/internal|external/` | 회의록 | `YYMMDD-` 필수 |
| `planning/` | BM·사업 전략 | `YYMMDD-` 필수 |
| `qa/` | QA 결과·테스트 핸드오프 | — |
| `research/` `partnerships/` `brand/` `terms/` | 각각의 용도 | — |

### Step 3: 구조 가드 검증 — 위반 시 중단

모노레포 `CLAUDE.md` "docs/ 구조 가드"는 **위반 상태에서 커밋을 금지**한다.
올리기 전에 아래를 모두 확인한다.

1. **서브디렉토리 금지** — 각 폴더는 플랫. 예외: `gdrive/` `personal/` `projects/` `meetings/internal|external/`
2. **위치 적합성** — 내용이 그 폴더의 허용 유형에 맞는가
3. **`guides/` 는 날짜 접두사 금지** — 날짜가 붙어야 할 내용이면 `features/` 로
4. **`features/` `planning/` `meetings/` 는 `YYMMDD-` 접두사 필수**
5. **바이너리 금지** — `.pdf` `.docx` `.hwp` `.pptx` `.xls(x)` `.csv` (예외: `terms/*.txt`)
6. **`projects/` 는 1단계까지** — `README.md` 필수(개요·현황·Drive 원본 위치), 문서는 `YYMMDD-` 접두사

**위반을 발견하면 PR을 만들지 말고 중단**하고 올바른 위치를 제안한다.
사용자가 명시적으로 승인한 경우에만 진행한다.

### Step 4: 브랜치 생성 및 문서 작성

모노레포 checkout은 사용자의 다른 작업이 올라가 있을 수 있으므로 **먼저 상태를 확인**한다.

```bash
cd company-src/oursymbol
git status --short                       # 더러우면 중단하고 사용자에게 알림
git checkout main && git pull origin main
git checkout -b docs/promote-<주제>-<YYMMDD>
```

문서를 작성한다. vault 원문 복붙이 아니라 **확정 문서 형태로 다시 쓴다.**
`features/` 라면 기존 문서의 헤더 형식(카테고리·상태 등)을 따른다.
문서 하단에 출처를 남긴다:

```md
> 출처: obsidian-vault `vault/06-docs/03-결정사항/260803-....md` (2026-08-03 회의)
```

### Step 5: PR 생성 — 자동 머지하지 않는다

```bash
git add docs/
git commit -m "docs(<카테고리>): <제목>"
git push -u origin docs/promote-<주제>-<YYMMDD>
gh pr create --title "..." --body "..." --reviewer <리뷰어>
```

**vault 레포와 달리 여기서는 자동 머지하지 않는다.** 모노레포는 코드 레포이고
사람 리뷰가 실제 게이트다. 리뷰어는 기본적으로 이준범.

PR 본문에 포함할 것:
- 승격한 결정 항목 목록
- 원본 회의일·참석자
- vault 원문 경로
- 함께 올리지 **않은** 보류 항목 (있다면 명시)

### Step 6: vault에 역링크 남기기

승격된 vault 원문 frontmatter에 추가한다. 이게 있어야 나중에
"이건 이미 정식 문서로 갔다"를 알 수 있고, 승격률 측정이 가능해진다.

```yaml
promoted_to: oursymbol/docs/features/260810-....md
promoted_pr: https://github.com/oursymbol/oursymbol/pull/123
promoted_at: 2026-08-10
```

그 뒤 vault 레포에서 `handoff` 와 동일한 방식으로 저장·동기화한다.

### Step 7: 모노레포 원상복구

```bash
cd company-src/oursymbol && git checkout main
```

모노레포 checkout은 vault에서 **읽기 참조용**이므로 작업 후 main으로 되돌린다.

### Step 8: 보고

```
정식 문서로 올렸습니다.

  대상: 260803 이벤트리서치 & 옵시디언 방향성 논의
  올린 곳: docs/features/260810-obsidian-vault-adoption.md
  승격한 결정: 6건
  올리지 않은 것: 보류 5건 (Sync 결제 여부 등) — vault에 그대로 있습니다

  검토 요청: https://github.com/oursymbol/oursymbol/pull/123
  → 이준범님이 확인하시면 반영됩니다.

vault 원문에도 "정식 문서로 올라감" 표시를 남겼습니다.
```

## 실패 시 대응

| 상황 | 대응 |
|---|---|
| 모노레포 작업트리가 더러움 | 중단. 남의 작업을 건드리지 않는다 |
| 구조 가드 위반 | 중단 + 올바른 위치 제안 |
| 모노레포 clone 없음 | 비개발자에게는 김규형님께 요청 안내 |
| PR 권한 없음 | 브랜치 push까지만 하고 URL 안내 |

## 관련

- 승격 대상 원본: `vault/06-docs/03-결정사항/`
- 승격하지 말아야 할 것의 근거: `vault/00-overview/vault-rationale.md` (배드 시나리오 1 — vault를 SSOT로 만들지 않는다)
- 모노레포 규칙 원문: `company-src/oursymbol/CLAUDE.md` "docs/ 구조 가드"
