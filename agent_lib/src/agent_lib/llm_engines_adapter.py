
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from llm_engines.contracts import ChatMessage, ChatModel, GenerationRequest, GenerationResponse

from .contracts import AgentAction, AgentContext, Planner


@dataclass(frozen=True)
class RoleEngineSet:
    planner: ChatModel
    executor: ChatModel | None = None
    critic: ChatModel | None = None
    fallback: ChatModel | None = None

    def get(self, role: str) -> ChatModel:
        normalized = str(role or 'planner').strip().lower()
        engine = {
            'planner': self.planner,
            'executor': self.executor or self.planner,
            'critic': self.critic or self.planner,
            'fallback': self.fallback or self.planner,
        }.get(normalized)
        if engine is None:
            raise KeyError(f'No engine configured for role: {role}')
        return engine

    def invoke(
        self,
        role: str,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> GenerationResponse:
        engine = self.get(role)
        request = GenerationRequest(
            messages=[
                ChatMessage(role='system', content=system_prompt),
                ChatMessage(role='user', content=user_prompt),
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            metadata=dict(metadata or {}),
        )
        return engine.generate(request)


def extract_json_object(text: str) -> dict[str, Any]:
    payload = (text or '').strip()
    if not payload:
        raise ValueError('Expected JSON response, got empty text.')
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        start = payload.find('{')
        end = payload.rfind('}')
        if start >= 0 and end > start:
            return json.loads(payload[start:end+1])
        raise


def _action_meta(response: GenerationResponse | None, *, engine_role: str) -> dict[str, Any]:
    usage = response.usage.model_dump() if (response is not None and hasattr(response.usage, 'model_dump')) else {}
    active = []
    if response is not None:
        for item in list(getattr(response, 'active_optimizations', []) or []):
            active.append(item.model_dump() if hasattr(item, 'model_dump') else dict(item))
    return {
        'engine_role': engine_role,
        'model_name': getattr(response, 'model_name', None),
        'backend': getattr(response, 'backend', None),
        'usage': usage,
        'active_optimizations': active,
    }


def action_from_payload(
    payload: dict[str, Any],
    *,
    response: GenerationResponse | None = None,
    engine_role: str | None = None,
) -> AgentAction:
    kind = str(payload.get('kind') or '').strip().lower()
    role = engine_role or 'planner'
    meta = dict(payload.get('meta') or {})
    meta.update(_action_meta(response, engine_role=role))
    if kind == 'tool':
        name = str(payload.get('tool_name') or payload.get('name') or '').strip()
        args = payload.get('arguments') or payload.get('args') or {}
        return AgentAction.tool(name, dict(args), message=str(payload.get('message') or ''), meta=meta)
    if kind == 'final':
        output = str(payload.get('final_output') or payload.get('output') or payload.get('message') or '')
        return AgentAction.final(output, meta=meta)
    if kind == 'message':
        return AgentAction.message_only(str(payload.get('message') or ''), meta=meta)
    raise ValueError(f'Unknown action payload kind: {kind!r}')


class LLMActionPlanner(Planner):
    def __init__(
        self,
        *,
        engines: RoleEngineSet,
        system_prompt: str,
        prompt_builder: Callable[[AgentContext], str],
        engine_role: str = 'planner',
        max_tokens: int = 300,
        temperature: float = 0.0,
    ) -> None:
        self.engines = engines
        self.system_prompt = system_prompt
        self.prompt_builder = prompt_builder
        self.engine_role = engine_role
        self.max_tokens = max_tokens
        self.temperature = temperature

    def plan(self, context: AgentContext) -> AgentAction:
        response = self.engines.invoke(
            self.engine_role,
            system_prompt=self.system_prompt,
            user_prompt=self.prompt_builder(context),
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            metadata={'task_id': context.task.task_id, 'controller': context.active_controller},
        )
        payload = extract_json_object(response.message.content or '')
        return action_from_payload(payload, response=response, engine_role=self.engine_role)
