"""TradingAgents 의 LLM 호출을 **로그인된 `claude` CLI(구독)** 로 보내는 어댑터.

── 왜 이렇게 하나 ───────────────────────────────────────────────────────────
TradingAgents 는 langchain_anthropic 으로 API 를 직접 부른다 → ANTHROPIC_API_KEY
(종량 과금)가 필요하다. 2026-11-06 결정: API 키 말고 **지금 쓰는 구독으로** 돌린다.

🔴 구독 OAuth 토큰을 꺼내 langchain 에 넣는 방식은 **쓰지 않는다.** Anthropic 약관상
OAuth 인증은 "Claude Code 와 Anthropic 네이티브 앱의 일반 사용" 전용이다
(code.claude.com/docs/en/legal-and-compliance). 허용되는 길은 **수정하지 않은
claude 바이너리를 본인 구독으로 실행하는 것**이고, 이 체인의 다른 단계
(market-snapshot·daily-conclusion)도 이미 그렇게 돈다. 그래서 LLM 호출 하나하나를
`claude -p` 프로세스로 바꾼다.

── 어떻게 ───────────────────────────────────────────────────────────────────
TradingAgents 가 LLM 에 요구하는 건 세 가지다:
  ① 그냥 대화  (researcher·debator·reflection)       → claude -p 텍스트
  ② bind_tools  (analyst 가 시세·뉴스·재무 도구 호출)  → JSON 스키마로 "도구 호출 or 최종답"을
                 받아 AIMessage.tool_calls 로 되돌린다. 도구 실행은 LangGraph 가 한다
  ③ with_structured_output (매니저·트레이더)          → --json-schema 의 structured_output
claude 자체 도구는 전부 끈다(--tools ""). 웹 검색 같은 걸로 TradingAgents 의
point-in-time 데이터(기준일까지만 보이는 데이터)를 우회하면 안 되기 때문이다.

── 격리 ─────────────────────────────────────────────────────────────────────
빈 디렉터리에서 --setting-sources=project 로 띄운다. 기본값으로 띄우면 전역
~/.claude/CLAUDE.md(OMC 오케스트레이션 지시)와 플러그인 훅이 매 호출에 섞여 들어간다
— 실측 입력 2817토큰 → 696토큰. ANTHROPIC_API_KEY 는 환경에서 지운다: 남아 있으면
claude 가 구독 대신 그 키로 과금한다.

── 비용·한도 ────────────────────────────────────────────────────────────────
과금은 없지만 **구독 사용 한도**를 쓴다. 종목당 호출 수십 번 × 6종목이다. 한도에
걸리면 claude 가 is_error 로 끝나고, 여기서 재시도 후 예외를 올린다 → 그 종목만
실패로 기록된다(§agent_review.py). 브리핑 단계(daily-conclusion)도 같은 한도를 쓰므로
agent-review 를 그 앞에 두는 한 동시 실행 수(--jobs)를 낮게 유지한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.utils.function_calling import convert_to_openai_tool

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", str(Path.home() / ".local/bin/claude"))
CALL_TIMEOUT = int(os.environ.get("TA_CLI_CALL_TIMEOUT", "300"))
RETRIES = int(os.environ.get("TA_CLI_RETRIES", "2"))
_WORKDIR = Path(tempfile.gettempdir()) / "ta-claude-cli"   # 빈 디렉터리 — CLAUDE.md 를 줍지 않게

# TradingAgents 설정에 쓰는 이름 → claude --model 에 넘길 이름.
# 별칭(sonnet/opus)은 항상 최신 모델을 가리킨다. 전체 ID 를 써도 그대로 넘어간다.
ALIASES = {"claude-sonnet-5": "sonnet", "claude-opus-5-5": "opus"}


class ClaudeCLIError(RuntimeError):
    pass


def run_claude(prompt: str, system: str, model: str, schema: dict | None = None) -> dict:
    """claude -p 한 번. 성공하면 CLI 의 JSON 결과(dict)를, 아니면 예외."""
    _WORKDIR.mkdir(exist_ok=True)
    cmd = [CLAUDE_BIN, "-p", "--model", ALIASES.get(model, model),
           "--tools", "", "--strict-mcp-config", "--no-session-persistence",
           "--setting-sources=project", "--system-prompt", system,
           "--output-format", "json"]
    if schema is not None:
        cmd += ["--json-schema", json.dumps(schema)]
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["DISABLE_OMC"] = "1"

    last = "?"
    for attempt in range(RETRIES + 1):
        if attempt:
            time.sleep(15 * attempt)
        try:
            # 프롬프트는 stdin 으로 — 도구 결과(시세 표·뉴스)가 붙으면 argv 한도를 넘을 수 있다
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                               timeout=CALL_TIMEOUT, cwd=_WORKDIR, env=env)
        except subprocess.TimeoutExpired:
            last = f"{CALL_TIMEOUT}초 초과"
            continue
        try:
            d = json.loads(p.stdout)
        except json.JSONDecodeError:
            last = f"rc={p.returncode} {(p.stderr or p.stdout).strip()[-300:]}"
            continue
        if d.get("is_error") or d.get("subtype") != "success":
            last = f"{d.get('subtype')} {str(d.get('result'))[:300]}"
            continue
        if schema is not None and d.get("structured_output") is None:
            last = "structured_output 없음"
            continue
        return d
    raise ClaudeCLIError(f"claude -p 실패 ({RETRIES + 1}회): {last}")


def _content(m: BaseMessage) -> str:
    c = m.content
    if isinstance(c, list):
        c = "\n".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in c)
    return str(c)


def render(messages: list[BaseMessage]) -> tuple[str, str]:
    """메시지 목록 → (system, transcript). claude -p 는 한 턴짜리라 대화를 글로 편다."""
    system = "\n\n".join(_content(m) for m in messages if isinstance(m, SystemMessage))
    parts = []
    for m in messages:
        if isinstance(m, SystemMessage):
            continue
        if isinstance(m, ToolMessage):
            parts.append(f"[TOOL RESULT: {m.name or 'tool'} (call {m.tool_call_id})]\n{_content(m)}")
        elif isinstance(m, AIMessage):
            said = _content(m)
            calls = "; ".join(f"{c['name']}({json.dumps(c['args'], default=str)})"
                              for c in (m.tool_calls or []))
            parts.append("[ASSISTANT]\n" + (said + ("\n" if said else "") +
                                            (f"[called tools: {calls}]" if calls else "")).strip())
        else:
            parts.append(f"[USER]\n{_content(m)}")
    return system, "\n\n".join(parts)


def _tool_schema(specs: list[dict]) -> dict:
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["call_tools", "final"]},
            "tool_calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "enum": [s["function"]["name"] for s in specs]},
                        "args": {"type": "object"},
                    },
                    "required": ["name", "args"],
                },
            },
            "content": {"type": "string", "description": "최종 답 (action=final 일 때)"},
        },
        "required": ["action"],
    }


def _tool_instructions(specs: list[dict]) -> str:
    lines = ["\n\n## Tools",
             "You can call the tools below. To call tools, answer with action=\"call_tools\" and "
             "tool_calls=[{name, args}] (args must follow the tool's JSON parameters). The results "
             "will come back as [TOOL RESULT] blocks in the next turn. When you have enough "
             "information, answer with action=\"final\" and put your full answer in content. "
             "Do not invent tool results."]
    for s in specs:
        f = s["function"]
        lines.append(f"- {f['name']}: {f.get('description', '').strip()}\n"
                     f"  parameters: {json.dumps(f.get('parameters', {}), ensure_ascii=False)}")
    return "\n".join(lines)


class ChatClaudeCLI(BaseChatModel):
    model: str = "sonnet"
    tool_specs: list[dict] | None = None

    @property
    def _llm_type(self) -> str:
        return "claude-cli"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        system, transcript = render(messages)
        system = system or "You are a helpful financial analysis assistant."
        if self.tool_specs:
            d = run_claude(transcript, system + _tool_instructions(self.tool_specs), self.model,
                           _tool_schema(self.tool_specs))
            out = d["structured_output"]
            calls = [dict(name=c["name"], args=c.get("args") or {}, id=f"call_{uuid.uuid4().hex[:12]}",
                          type="tool_call")
                     for c in (out.get("tool_calls") or [])] if out.get("action") == "call_tools" else []
            msg = AIMessage(content="" if calls else (out.get("content") or ""), tool_calls=calls)
        else:
            d = run_claude(transcript, system, self.model)
            msg = AIMessage(content=d.get("result") or "")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(update={"tool_specs": [convert_to_openai_tool(t) for t in tools]})

    def with_structured_output(self, schema, *, include_raw: bool = False, **kwargs):
        if include_raw:
            raise NotImplementedError("include_raw 미지원")
        is_model = isinstance(schema, type) and hasattr(schema, "model_json_schema")
        js = schema.model_json_schema() if is_model else convert_to_openai_tool(schema)["function"]["parameters"]

        def call(inp):
            msgs = self._convert_input(inp).to_messages()
            system, transcript = render(msgs)
            d = run_claude(transcript, system or "You are a careful financial analyst.", self.model, js)
            return schema.model_validate(d["structured_output"]) if is_model else d["structured_output"]

        return RunnableLambda(call)


def install(provider_name: str = "claude_cli") -> None:
    """TradingAgents 의 provider 팩토리에 'claude_cli' 를 끼워 넣는다.

    create_tier_client 가 같은 모듈의 create_llm_client 를 전역 이름으로 부르므로
    모듈 속성을 바꾸면 거기로 들어온다. 다른 provider 는 원래 함수로 넘긴다.
    """
    from tradingagents.llm_clients import factory
    from tradingagents.llm_clients.base_client import BaseLLMClient

    class ClaudeCLIClient(BaseLLMClient):
        provider = provider_name

        def get_llm(self):
            return ChatClaudeCLI(model=self.model)

        def validate_model(self):
            return True

    if getattr(factory.create_llm_client, "_claude_cli", False):
        return
    original = factory.create_llm_client

    def patched(provider, model, base_url=None, **kwargs):
        if provider.lower() == provider_name:
            return ClaudeCLIClient(model, base_url)
        return original(provider, model, base_url, **kwargs)

    patched._claude_cli = True
    factory.create_llm_client = patched
