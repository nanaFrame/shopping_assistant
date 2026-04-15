"""ContextMerge — merges current user message with session history."""

from __future__ import annotations

from app.agent.state import AgentState


async def context_merge(state: AgentState) -> dict:
    messages = list(state.get("messages") or [])
    messages.append({"role": "user", "content": state.get("user_message", "")})

    return {
        "messages": messages,
        "user_requirements": state.get("user_requirements") or {},
        "hard_constraints": state.get("hard_constraints") or {},
        "soft_preferences": state.get("soft_preferences") or {},
    }
