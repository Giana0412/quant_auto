# LC Ghosts 위키

이 폴더는 **LLM 이 유지보수하는 지식베이스**다.
([Karpathy, LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 패턴)

## 왜 만들었나

지식이 세 군데로 흩어져 있었다:
- `README.md` 413줄 — 실행법과 설계 근거가 뒤섞여 계속 비대해짐
- `market_metrics.py` 1,347줄 중 **26%가 한글 산문** — "왜 이렇게 했나"가 코드에 갇힘 [측정 2026-09-21]
- `~/Downloads/` — 회의록·교수 자문·리포트 원본이 파일로만 존재

그래서 **같은 질문에 두 번 답을 찾아야 했고**, 판단이 번복돼도 기록이 안 남았다
(실제로 `VOL_PENALTY` 근거가 이틀 만에 뒤집혔고, 지도교수 전략 권고가 사흘 새 두 번 바뀌었다).

## 세 층

| 층 | 무엇 | 어디 |
|---|---|---|
| **원본** | 회의록·자문 전사본·리포트 PDF. **절대 수정하지 않는다** | `~/Downloads/` · `wiki/sources.md` 에 등록 |
| **위키** | LLM 이 쓰고 고치는 마크다운. **이 폴더** | `wiki/**` |
| **스키마** | 구조와 규칙. **이 파일** | `wiki/index.md` |

## 페이지

| 페이지 | 무엇을 담나 |
|---|---|
| [sources.md](sources.md) | 원본 문서 대장 — 무엇을 언제 읽었나 |
| [competition/rules.md](competition/rules.md) | 대회 규정 · **확정/미확정 표시 필수** |
| [competition/timeline.md](competition/timeline.md) | 일정 |
| `advice/contradictions.md` (로컬 전용) | 🔴 **충돌 대장** — 조언이 서로 다를 때 |
| `advice/` (로컬 전용) | 교수 A 자문 |
| `advice/` (로컬 전용) | 교수 B 자문 |
| [strategy/decisions.md](strategy/decisions.md) | 결정 로그 — **번복 이력 포함** |
| [strategy/open-questions.md](strategy/open-questions.md) | 🔴 **미확인 사항** |
| [pipeline/design-rationale.md](pipeline/design-rationale.md) | 파이프라인 설계 근거 |
| [pipeline/findings.md](pipeline/findings.md) | 실측 결과 — **날짜 필수** |

## 규칙 — 이걸 지켜야 위키가 썩지 않는다

1. **모든 주장에 출처와 날짜를 붙인다.**
   `금융 26Q3 성장률 +5.4% [LSEG 26Q2 리포트, 2026-09-18]`
   출처 없는 문장은 린트가 잡는다.

2. **확정과 추정을 섞지 않는다.** `✅확정` / `⚠️미확인` / `❌반증됨` 중 하나를 단다.
   회의록 자체가 "음성 인식 기반이라 날짜·고유명사는 원문 확인 필요"라고 단서를 달았다.

3. **틀린 걸 지우지 않는다.** 취소선과 정정 사유를 남긴다.
   *왜* — 같은 실수를 두 번 하지 않으려면 왜 틀렸는지가 필요하다.

4. **충돌은 해소하지 말고 기록한다.** 두 교수님이 정반대를 말했을 때 한쪽을 지우면
   나중에 "왜 이렇게 정했지"를 복원할 수 없다. → `advice/contradictions.md`

5. **코드 주석과 역할을 나눈다.**
   코드 주석 = *이 코드가 왜 이런가* / 위키 = *우리가 무엇을 알고 어떻게 알았나*

## 작업

```bash
python3 .automation/wiki_lint.py        # 출처 없는 주장·묵은 미확인·끊긴 링크 점검
```

- **ingest** — 새 원본이 오면 `sources.md` 에 등록하고 영향받는 페이지를 갱신한다
- **query** — 위키를 먼저 찾고, 없을 때만 원본을 다시 읽는다
- **lint** — 주기적으로. 미확인이 오래 묵으면 그 자체가 리스크다
