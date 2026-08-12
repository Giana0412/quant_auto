---
created: 2026-08-06
updated: 2026-08-10
source: Google Drive — "옵시디언 리서치 w 아워심볼 구조 PainPoint" (작성일 2026-07-29, 김규형)
source_url: https://docs.google.com/document/d/1JXiVZA72NE4m4saeDW9X0lWHsHXAq-aHtaQp_Q2i8EM/edit
---

# 이 Vault는 왜 존재하는가

이 vault(Obsidian 도입)는 즉흥적 개인 실험이 아니라, 이 세션이 시작되기 며칠 전(2026-07-29) 이미 문서화된 **회사 이니셔티브**다. 원본은 Google Drive에 살아있는 문서로 계속 갱신될 수 있으므로, 이 노트는 그 요약이며 정본은 위 `source_url`이다.

## 도입 배경 (원본 요지)

- OAO 모노레포에는 프론트엔드·백엔드·연구 스크립트·Symba 인프라·각종 docs가 한 저장소에 얹혀 있음
- 현재도 AI 에이전트(Symba)를 활발히 쓰고 있고, 장기적으로 팀별/개인별 전문 비서 에이전트 + 오케스트레이터 구조를 지향
- 그런데 실제 맥락은 git, Notion, Slack, 이메일, Drive에 분산돼 있고 서로 연결도 안 돼 있음 → 에이전트가 팀 상황을 부분적으로만 이해 + 사람도 같은 설명을 반복하는 병목 발생

## 가장 활성화가 안 된 4개 영역 (문제 진단)

1. `docs/brand`, `docs/partnerships` — 3~4개월 커밋 0건
2. `frontend/together` — 9주 업데이트 없음
3. `backend/services/kor-triathlon-image-service` 외 4개 — 9주 변경 없음
4. `docs/meetings` — 7주 업데이트 없음 (당시 기준)

2·3은 코드베이스라 git 관리가 맞는 것으로 판단(다만 "왜 멈췄는지" 맥락은 남길 수 있음). **1·4가 Obsidian이 도움이 될 영역**으로 지목됨.

## 왜 git 모노레포만으로는 부족한가

- git은 코드와 "확정된 문서"에 최적화 — 버전관리·리뷰·배포 파이프라인과 바로 연결됨
- 하지만 브랜드/파트너십/세일즈/회의는 초안·가설·중간 의사결정이 자주 바뀌는 "거친 원재료" 성격 — 그대로 git에 커밋하면 노이즈가 크고, 실행 코드와 실험 내러티브가 섞여 가독성이 떨어짐
- Obsidian은 이 "중간 맥락"을 실시간으로 저장하는 캡처 레이어 역할 — 첫 결정부터 최종 결정까지의 과정이 남으면, 나중에 에이전트를 훈련시킬 때도 유용하다는 관점

## 문서 관점 / 세일즈 관점 / 회의 관점 / 에이전트 관점 (4개 축)

원본은 각 관점에서 왜 지금 구조가 부족한지 짚는다 — 세일즈 맥락(공이 누구에게 있는지, 마지막 미팅무브, 막힌 이유)이 이메일·구두·Slack·Notion에 흩어져 매번 재구성해서 설명해야 하는 비효율, 회의 직후 거친 메모를 바로 git에 커밋하기엔 마찰이 커서 `docs/meetings` 공백이 반복되는 문제 등.

## 제안된 해법 (TBC 표시, 확정 아님)

- Obsidian을 캡처/청사진 레이어로: 회의 끝나고 3분 안에 요약·결정·보류·다음 액션 기록 (혹은 클로바노트) — **지금 이 vault의 `06-docs` 파이프라인(전사본/정리본/결정사항)이 이 제안을 그대로 구현한 것**
- 세일즈 맥락용 `sales/pipelines/{partner}.md` 고정 필드 아이디어(Our ball/Their ball, Last contact, Next action, Block reason 등) — **아직 이 vault에 구현되지 않음**

## 명시된 위험 (배드 시나리오)

1. **Obsidian을 공식 source of truth로 만드는 것** — Symba가 `/oao/docs`와 Obsidian 둘 다 봐야 하고, 어느 쪽이 최신인지 헷갈리고, "git이 single source of truth"라는 OAO 원칙이 깨짐
2. **vault만 만들고 승격 루틴이 없는 것** — 그냥 메모 무덤이 됨. `docs/meetings` 공백 문제가 이미 있는데 Obsidian 도입만 하고 git으로 승격하는 루틴이 없으면 문서가 한 곳 더 늘어날 뿐

## 원본의 타임라인 (2026-07-29 기준 계획)

- 국가 넓히기 (event research discover): ~8/7 — **"옵시디언 개인 테스트"**
- 종목 넓히기: ~8/14 — **"옵시디언 전사 도입"**

이 세션(2026-08-05~06)은 이 계획의 "옵시디언 개인 테스트" 단계에 해당한다.

## 참고한 외부 사례 (원본에 인용됨)

- MCP + Obsidian + StateGraph 기반 로컬퍼스트 상태형 멀티에이전트 사례 — vault를 working memory로 쓰는 패턴, `00-index.md`/`decisions/`/`specs/`/`phases/`/`reports/` 같은 "살아있는 프로젝트 레저" 구조
- 여러 AI harness가 공유하는 shared_memory 레이어를 vault 안에 설계한 사례 — "human notes = source, agent notes = 별도 레이어" 원칙, `memory_queue → human 승인 → wiki 승격` 흐름

## 관련 문서
- [[oao-wiki-설계문서]] — 이 기획서를 받아 실제 설계로 구체화한 문서 (10개 항목 답변 + 결정 요청)
- [[project-summary]]
- [[../06-docs/_템플릿-가이드|06-docs 템플릿 가이드]] (이 기획서의 "회의 직후 3분 요약" 제안을 구현한 것)
