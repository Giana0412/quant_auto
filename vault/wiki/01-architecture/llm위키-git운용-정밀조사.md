---
created: 2026-08-14
updated: 2026-08-14
owner: 김규형
purpose: llm-wiki 를 git 으로 운용하는 사람들이 실제로 쓰는 기법 — 구현체 20여 개 정밀 조사
review_by: 2026-08-19
---

# llm-wiki × git 운용 정밀조사

> GitHub 을 훑어 llm-wiki 구현체 **20여 개**를 찾고, **git 을 어떻게 다루는지**만 뽑았다.
> 도구 소개가 아니라 **커밋·충돌·훅·인덱스 처리 기법** 위주다.

---

## 0. 세 줄 요약

**1. 🔴 거의 아무도 팀 싱크를 안 푼다.** 20여 개 중 다중 사용자 동시 쓰기를 다룬 건
[stigmergy](https://github.com/sturlese/stigmergy) 하나다. **제3자가 쓴 생태계 조사조차
git·sync·team 을 아예 안 다룬다.**

**2. 🔴 대신 "에이전트가 사람 작업을 덮어쓰는 것"은 다들 최우선으로 막는다.**
네 구현체가 각각 다른 방법으로 같은 위험을 막는다 (§2).

**3. 🔴 index 충돌은 이미 풀린 문제였다.** [kfchou/wiki-skills](https://github.com/kfchou/wiki-skills)
는 **`index.md` 를 아예 gitignore 하고 매번 재생성**한다 — 그러면 충돌 자체가 불가능하다.

---

## 1. 찾은 구현체 목록

`llm-wiki` · `karpathy wiki` 등으로 GitHub 검색한 결과 상위권.

| 구현체 | ★ | 성격 |
|---|---|---|
| [TencentCloud/TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory) | 21.2k | "팀급 메모리 허브" 표방 — **실제론 단일 에이전트** |
| [Tencent/WeKnora](https://github.com/Tencent/WeKnora) | 19.8k | RAG 플랫폼 |
| [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) | 16.3k | 크로스플랫폼 데스크톱 앱 |
| [AgriciDaniel/claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) | 10.8k | **Obsidian + Claude Code 최대** |
| [inkeep/open-knowledge](https://github.com/inkeep/open-knowledge) | 3.4k | 🔴 **"git/GitHub 으로 팀 공유·자동싱크"** |
| [SamurAIGPT/llm-wiki-agent](https://github.com/SamurAIGPT/llm-wiki-agent) | 3.4k | 다중 CLI 지원 |
| [sdyckjq-lab/llm-wiki-skill](https://github.com/sdyckjq-lab/llm-wiki-skill) | 2.3k | 중국어권 스킬 |
| [atomicstrata/llm-wiki-compiler](https://github.com/atomicstrata/llm-wiki-compiler) | 1.9k | "지식 컴파일러" |
| [Astro-Han/karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki) | 1.9k | Claude·Cursor·Codex 호환 |
| [skyllwt/AutoSci](https://github.com/skyllwt/AutoSci) | 1.6k | 연구 플랫폼 |
| [lucasastorian/llmwiki](https://github.com/lucasastorian/llmwiki) | 1.5k | 오픈소스 구현 |
| [kytmanov/obsidian-llm-wiki-local](https://github.com/kytmanov/obsidian-llm-wiki-local) | 801 | 100% 로컬(Ollama) |
| [swarmclawai/swarmvault](https://github.com/swarmclawai/swarmvault) | 655 | 지식그래프 |
| [kfchou/wiki-skills](https://github.com/kfchou/wiki-skills) | ~160 | 🔴 **git 처리가 가장 구체적** |
| [alfadur7/llm-wiki-newsroom](https://github.com/alfadur7/llm-wiki-newsroom) | 76 | 🔴 **다중 에이전트 편집국** |
| [vanillaflava/llm-wiki-skills](https://github.com/vanillaflava/llm-wiki-skills) | 59 | 스킬 6종 |
| [ddsyasas/llm-wiki](https://github.com/ddsyasas/llm-wiki) · [cobusgreyling/llm-wiki](https://github.com/cobusgreyling/llm-wiki) | 37·39 | 로컬 우선 |
| [stjbrown/agent-knowledge](https://github.com/stjbrown/agent-knowledge) | 26 | **OKF 규격 + 생태계 조사** |
| [eugenelim/llm-wiki-kit](https://github.com/eugenelim/llm-wiki-kit) | 11 | "팀용" 표방 — **실제론 개인용** |
| [sturlese/stigmergy](https://github.com/sturlese/stigmergy) | 5 | ✅ **유일하게 팀 싱크를 품** |

> **★ 과 팀 지원은 무관하다.** 2만 개짜리도 단일 사용자고, 5개짜리가 유일하게 팀을 푼다.

---

## 2. 🔴 다들 막는 것 — "에이전트가 사람 작업을 덮어쓰기"

네 구현체가 **각각 다른 방법으로 같은 위험**을 막는다. 독립 수렴이라 신호가 강하다.

| 구현체 | 방법 |
|---|---|
| [llm-wiki-kit](https://github.com/eugenelim/llm-wiki-kit) | 🔴 **제안 사이드카** — *"사람이 편집한 파일을 **조용히 덮어쓰지 않는다**. 모든 쓰기가 `safe_write` 를 거친다"*. 충돌하면 `.proposed` 파일로 떨어지고 **사람이 검토** |
| [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) | 🔴 **SHA-256 낙관적 동시성** — *"모든 대상을 읽고 **예상 SHA-256 을 기록**"* 한 뒤, 적용 시점에 다르면 중단 |
| [kfchou/wiki-skills](https://github.com/kfchou/wiki-skills) | 🔴 **pre-commit 훅으로 차단** (§3-2) |
| [stigmergy](https://github.com/sturlese/stigmergy) | **일회용 worktree + 게이트 8종** |

> **준범님 안은 정반대 방향이다.** *"자가 치유: 사람이 에디터로 직접 고치는 것은 막지 않되,
> **다음 lint 패스에서 에이전트가 복원한다**"* — 사람 편집을 **되돌린다.**
>
> 원칙("모든 문서는 에이전트를 통해서만")상 일관되지만, **실수로 고친 사람은 작업을 잃는다.**
> 위 넷은 전부 **사람 편집을 보호**하는 쪽이다. 어느 쪽이 맞는지는 정책 판단이지만,
> **네 구현체가 반대로 갔다는 사실은 알고 정해야 한다.**

---

## 3. 🔴 kfchou/wiki-skills — git 처리가 가장 구체적

★160 으로 작지만, **git 을 다루는 기법이 조사한 것 중 제일 촘촘하다.**
(제3자 생태계 조사도 *"우리 계획과 형태가 가장 가깝다"* 며 이걸 참조 구현으로 꼽았다.)

### 3-1. 🔴 `index.md` 를 git 에서 뺀다

> *"인덱스는 **페이지 프론트매터에서 자동 생성**되며 **손으로 유지하지 않는다.**
> `wiki/index.md` 는 **gitignore 되고**, 읽기·쓰기 **전마다 재생성**된다."*

**충돌이 구조적으로 불가능해진다.** 파일이 git 에 없으니까.

| 우리 상황에 대입 | |
|---|---|
| 실측: 같은 날 두 명이 각각 ingest 하면 `index.md` **충돌** | 이 방식이면 **발생 자체가 안 함** |
| 준범님 규약 *"index.md 가 유일한 카탈로그"* | ✅ 유지됨 — 위치도 역할도 그대로, **git 에서만 뺀다** |
| 한 줄 요약을 누가 쓰나 | ⚠️ **프론트매터에서 생성**한다. 준범님 규격엔 요약 필드가 없음 (`purpose` 같은 게 필요) |

> **내가 제안했던 "index 를 생성물로"(A-3) 의 선례가 이것이다.** 그리고 저쪽은 한 발 더
> 나갔다 — **아예 git 에서 뺀다.** 재생성 가능한 것을 버전관리할 이유가 없다는 논리.

### 3-2. 🔴 pre-commit 훅이 커밋을 막는다

> *"**git 위키에 한해**, 페이지에 **해소되지 않은 모순 플래그**나 **구조적 문제**
> (프론트매터 누락, 깨진 `[[링크]]`, **슬러그 충돌**)가 있으면 pre-commit 훅이 커밋을 막는다."*

**stigmergy 의 게이트 8종을 가장 싸게 구현한 형태다.** 서버도 큐도 없이 **git 훅 하나**.

우리 `wiki_lint.py` 는 이미 이 검사들을 한다 — **L1(깨진 링크)·L3(프론트매터)·L2**.
**보고를 차단으로 바꾸는 데 필요한 건 훅 파일 하나**다.

### 3-3. 커밋 메시지에 `Wiki-Op:` 트레일러

> *"git 위키는 오퍼레이션을 **`Wiki-Op:` 트레일러가 붙은 커밋으로** 기록한다."*
> git 이 아닌 위키는 `wiki/log.md` 로 폴백. `bin/render-log.py` 가 필요할 때 이력을 렌더.

**git 이력 자체가 운영 로그가 된다.** 별도 로그 파일과 이중 기록이 안 생긴다.

> 준범님은 *"git 이 원천 장부, `log/` 는 의미 장부 — 층위가 달라 겹치지 않는다"* 로
> **둘 다 쓰기로** 정리했다. 이쪽은 **하나로 합쳤다.** 둘 다 근거 있는 선택이다.

### 3-4. 자동 커밋을 하지 않는다

> *"스킬은 커밋을 **제안하고**, 사용자가 **확인한다**. (자동 커밋 없음)"*

[claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) 도 같다:
> *"**어떤 명령도 자동으로 push·태그·발행·이슈·릴리스를 하지 않는다.**"*

[hippocampus](https://github.com/sturlese/hippocampus) 는 중간:
> Stop 훅이 **로컬 자동 커밋**, **push 는 수동.**

> **준범님 안은 자동 push 까지 간다** (*"commit 후 즉시 push 로 끝"*).
> 팀 공유가 목적이라 맞는 선택이지만, **조사한 셋은 전부 사람 확인을 남겨뒀다.**

### 3-5. 우리에게 없는 스킬 3종

| 스킬 | 무엇 |
|---|---|
| 🔴 **`wiki-update`** | 지식이 바뀌면 페이지를 고친다 — *"**항상 diff 를 먼저 보여준다**"* |
| 🔴 **`wiki-audit`** | 인용을 소스와 대조 검증. *"strong 모드는 **교차 모델 리뷰**를 추가"* |
| 🔴 **`wiki-merge`** | 중복 페이지 통합 / 과부하된 개념 분할 |

`wiki-update` 가 우리가 계속 지적한 **"기존 문서 갱신"** 이고, 여기선 **별도 스킬**이다.

### 3-6. lint 출력 형식

> *"심각도 등급이 매겨진 리포트(**🔴 errors / 🟡 warnings / 🔵 info**)를 **타임스탬프
> 페이지로** 쓰고, 수정을 제안하고, **무조건 로그를 남긴다.**"*

우리 lint 는 등급이 없다. **차단할 것(🔴)과 알림만 할 것(🔵)을 나누는 게 3-2 의 전제다.**

---

## 4. 충돌을 "잘 푸는" 대신 "안 나게" 하는 설계

### 4-1. 🔴 순차 체인 — [llm-wiki-newsroom](https://github.com/alfadur7/llm-wiki-newsroom)

한국 신문사 조직을 본떠 에이전트 5개를 둔다.

```
기자(reporter) → 칼럼니스트(columnist) → 교열(copyeditor) → 데스크(desk) → 편집국장
   원문 근거          종합·분석            자동 lint          질적 리뷰      게이트·에스컬레이션
```

> 🔴 *"**모든 역량 영역에 정확히 하나의 소유 역할**이 있고, 다역할 작업은
> **병렬 병합이 아니라 순차 체인**으로 돈다."*
> 교열은 글을 못 쓰고, 데스크는 lint 를 못 돌리고, 칼럼니스트는 게이트를 통과 못 하면 발행 못 한다.

**충돌을 병합으로 푸는 게 아니라 동시에 안 하게 만든다.** 사람도 같은 논리가 적용된다 —
Obsidian 팀 볼트 보고의 *"노트당 작성자 1명"* 규범과 같은 것을 **역할로 형식화**했다.

### 4-2. 큐 + 재시도 — [stigmergy](https://github.com/sturlese/stigmergy)

> *"worktree 의 base 커밋이 어긋나면 **push 가 실패하고 그 아이템은 다음 워커의 큐로
> 되돌아간다**"* / *"죽은 워커는 **배달 한 번을 잃을 뿐 캡처를 잃지 않는다**"*

**충돌을 풀지 않고 처음부터 다시 한다.**

### 4-3. git 을 숨긴다 — [inkeep/open-knowledge](https://github.com/inkeep/open-knowledge) ★3.4k

> *"**노코드 팀 공유와 자동 싱크를 git/GitHub 이 뒤에서 처리**한다."*

사용자는 git 명령을 안 친다. **다만 병합 전략·충돌 처리는 문서화돼 있지 않다** —
"자동 싱크"라고만 하고 어떻게 푸는지는 안 밝힌다.

---

## 5. `merge=union` 선례 — 여전히 못 찾음

내가 제안한 `.gitattributes` `merge=union` 의 선례를 다시 찾아봤다.

| 확인 | 결과 |
|---|---|
| [vanillaflava/llm-wiki-skills](https://github.com/vanillaflava/llm-wiki-skills) `.gitattributes` | main 브랜치에 없음(404) |
| [stjbrown/agent-knowledge](https://github.com/stjbrown/agent-knowledge) `.gitattributes` | **공백 보존용**(`whitespace=-trailing-space`)이지 병합용 아님 |
| GitHub 코드 검색 | 인증 필요로 조회 불가 |

> **결론: llm-wiki 계열에서 `merge=union` 선례는 확인 못 했다.**
> 대신 **kfchou 의 "index 를 gitignore" 가 같은 문제를 더 근본적으로 푼다** —
> 병합할 필요를 없애버린다. **A-3 를 A-2 보다 위로 올려야 한다.**

---

## 6. 우리에게 옮길 것 — 우선순위 갱신

| # | 무엇 | 출처 | 왜 |
|---|---|---|---|
| 1 | 🔴 **`index.md` 를 gitignore + 매번 재생성** | [kfchou/wiki-skills](https://github.com/kfchou/wiki-skills) | 충돌이 **구조적으로 불가능**해짐. 우리 `wiki_index.py` 가 이미 재생성한다 |
| 2 | 🔴 **pre-commit 훅으로 lint 차단** | 〃 | 게이트를 **훅 하나**로. 우리 lint 가 이미 검사함 |
| 3 | 🔴 **lint 에 심각도 등급** (🔴/🟡/🔵) | 〃 | 2번의 전제 — 차단할 것과 알림만 할 것 구분 |
| 4 | **`wiki-update` 스킬** (diff 먼저) | 〃 | 우리가 계속 지적한 "기존 문서 갱신" |
| 5 | **충돌 = 재시도** | [stigmergy](https://github.com/sturlese/stigmergy) | 미검증 항목이 사라짐 |
| 6 | **역할당 소유 영역 1개 + 순차 체인** | [newsroom](https://github.com/alfadur7/llm-wiki-newsroom) | 사람 쪽에도 적용 — 페이지 주인 |
| 7 | **커밋 트레일러** `Wiki-Op:` | [kfchou](https://github.com/kfchou/wiki-skills) | 검토용 — 준범님은 이중 장부로 이미 정리 |
| 8 | **`wiki-audit`** (인용 검증, 교차 모델) | 〃 | query 규칙이 "출처 필수"인데 검증기가 없음 |

---

## 7. 정책 판단이 필요한 것 — 조사가 반대로 가리킨다

| | 준범님 안 | 조사한 구현체들 |
|---|---|---|
| 사람이 직접 편집하면 | **lint 가 복원** | 🔴 **4곳이 전부 사람 편집을 보호** (사이드카·SHA·훅·worktree) |
| 커밋·푸시 | **자동 push 까지** | 🔴 **3곳이 사람 확인을 남김** ("자동 커밋 없음") |
| index | git 에 포함, 트랜잭션마다 갱신 | 🔴 **gitignore + 재생성** |

**셋 다 준범님 원칙에서는 일관된 선택이다** — "모든 쓰기가 에이전트를 통과한다"를
전제하면 복원도 자동 push 도 맞다. 다만 **그 전제가 깨지는 순간**(사람이 실수로 고침,
앱이 자동 커밋함) 손실이 생긴다. **조사한 구현체들은 그 전제를 안 믿는 쪽에 걸었다.**

---

## 8. 이번 조사에서도 확인 안 된 것

| | |
|---|---|
| 실제 팀이 llm-wiki 를 **몇 명이서 몇 달** 굴린 사례 | 🔴 **하나도 못 찾음.** 전부 도구이고, 운영 후기가 없다 |
| [inkeep/open-knowledge](https://github.com/inkeep/open-knowledge) 의 충돌 처리 | "자동 싱크"라고만 하고 미문서화 |
| `merge=union` 선례 | 못 찾음 (§5) |
| stigmergy 게이트 8종의 판정 기준 | 이름만 확인 |

> **가장 중요한 공백은 첫 줄이다.** 이 패턴을 **팀으로 오래 굴린 사람의 기록이 없다.**
> 우리가 그걸 처음 쓰게 될 가능성이 높고, 그래서 **초기 지표(§[[운영-온보딩-제안]] §8)를
> 재두는 게 중요하다.**

---

## 관련 문서
- [[구현체-운영구조-비교]] — stigmergy·hippocampus 운영 매뉴얼 원문
- [[싱크-사례별-장단점]] — 도구별 장단점
- [[운영-온보딩-제안]] — 사람 쪽 운영·온보딩
- [[사례조사-실사용패턴]] · [[레퍼런스-정밀대조]] · [[사례조사-LLM위키]]
