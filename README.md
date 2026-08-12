# OAO Wiki

회사의 회의·결정·맥락을 모아두는 단일 저장소입니다.
사람과 AI 에이전트가 **같은 기록을 읽고** 일하는 것이 목적입니다.

> **옵시디언 = 기억 / 헤르메스 = 머리 / 오르카 = 손발** — 260803 결정 13번

---

## 처음 오셨다면

| 목적 | 문서 |
|---|---|
| **설계 전체를 보고 싶다** | [설계문서](vault/wiki/00-overview/oao-wiki-설계문서.md) ← **여기부터.** 상단에 *바뀐 것 / 미정 / 피드백 요청* 세 가지가 있습니다 |
| 기술 배경 없이 읽고 싶다 | [쉬운 설명](vault/wiki/00-overview/oao-wiki-설계문서-쉬운설명.md) |
| 왜 만들었는지 | [vault-rationale](vault/wiki/00-overview/vault-rationale.md) |
| 어디에 뭐가 있는지 | [문서 지도](vault/index/문서지도.md) · [회의 목차](vault/index/회의.md) |

---

## 폴더 구조

층을 가르는 기준은 주제가 아니라 **"누가 고칠 수 있는가"** 입니다.

```
vault/
├── raw/      원본.      아무도 고치지 않는다
├── wiki/     정리된 지식. 에이전트가 갱신한다
├── schema/   운영 규칙.   사람만 고친다
├── index/    목차.       자동 생성
└── log/      이력.       쌓기만 한다
```

**Obsidian 으로 열 때는 레포 루트가 아니라 `vault/` 폴더를 여세요.**

---

## 규칙 (schema)

| | |
|---|---|
| 어느 폴더에 둘지 | [폴더 규칙](vault/schema/폴더-규칙.md) |
| 문서 맨 위 메타데이터 | [프론트매터 규격](vault/schema/프론트매터-규격.md) |
| 문서끼리 잇는 법 · 태그 | [링크 규칙](vault/schema/링크-규칙.md) |
| 규칙이 지켜지는지 점검 | [lint 규칙](vault/schema/lint-규칙.md) |
| 질문에 근거로 답하는 규약 | [query 규칙](vault/schema/query-규칙.md) |
| 에이전트가 언제 무엇을 하는가 | [에이전트 역할](vault/schema/에이전트-역할.md) |
| 회의록 3종 형식 | [템플릿 가이드](vault/schema/템플릿-가이드.md) |

> **에이전트가 실제로 로드하는 건 레포 루트의 `CLAUDE.md`** (위 규칙들의 압축판)입니다.
> Obsidian 에서는 `vault/` 만 보이므로 그 파일은 안 보입니다 — **규칙을 바꾸면 둘 다 고쳐야 합니다.**

---

## 자동화

| 언제 | 무엇 |
|---|---|
| 1시간마다 | Slack 원본 수집 → 회의록 3종 생성 → 목차 갱신 |
| 매주 월 09:30 | 규칙 위반 점검 → [리포트](vault/log/lint-report.md) |
| 요청 시 | 스킬 4종 — `handoff`(정리·공유) · `ask`(근거 조회) · `resolve-conflict`(충돌) · `promote`(코드 종속 문서 파생) |

동작 원리: [자동화 동작구조](vault/wiki/01-architecture/자동화-동작구조.md) · [전체 구조도](vault/wiki/01-architecture/전체-구조도.md)

```bash
python3 .automation/wiki_lint.py     # 규칙 점검 (보고만, 고치지 않음)
python3 .automation/wiki_index.py    # 목차 재생성
```

---

## 이 레포에 없는 것

| | 어디로 |
|---|---|
| PDF·이미지·PPT·녹음 | Google Drive (링크만 vault 에) |
| 코드에 종속된 문서 (기능 명세·API·QA) | 모노레포 `docs/` |
| 토큰·비밀번호 | `.automation/*.env` — gitignore, 커밋 금지 |
| 개인 데이터 | 별도 로컬 저장소 |

**판정 기준은 하나입니다** — *"이 문서는 코드가 바뀌면 같이 바뀌어야 하나?"*
YES 면 모노레포, NO 면 여기입니다. 확정돼도 여기 남습니다.

---

> 현재 개인 테스트 저장소입니다. 문의: 김규형
