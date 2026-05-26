import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.ai.providers import AIProviderError, provider_for_name
from app.ai.rule_planner import build_rule_based_plan
from app.core.config import settings
from app.core.security import hash_prompt
from app.database.models import PromptCache
from app.schemas.test import TestStep


class PlanningError(RuntimeError):
    pass


class AIOrchestrator:
    """Turns plain English into validated JSON steps with provider fallback and caching."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def plan_steps(
        self,
        prompt: str,
        base_url: str | None,
        workflow_context: str | None = None,
    ) -> tuple[list[TestStep], dict[str, Any]]:
        cache_prompt = f"{prompt}\ncontext:{workflow_context or ''}"
        cache_key = hash_prompt(cache_prompt, base_url, PROMPT_VERSION)
        if settings.AI_CACHE_ENABLED:
            cached = await self.db.get(PromptCache, cache_key)
            if cached:
                steps = self._normalize_steps([TestStep.model_validate(item) for item in cached.steps_json])
                steps = self._contextualize_steps(prompt, base_url, workflow_context, steps)
                return steps, {"provider": cached.provider, "model": cached.model, "cache_hit": True}

        specialist_steps = build_rule_based_plan(prompt, base_url, workflow_context)
        if self._should_prefer_specialist_plan(prompt, specialist_steps):
            return specialist_steps, {"provider": "deterministic-specialist", "model": "rules", "cache_hit": False}

        user_prompt = build_user_prompt(prompt, base_url, workflow_context)
        errors: list[str] = []

        for provider_name in settings.provider_order:
            try:
                provider = provider_for_name(provider_name)
                response = await provider.generate(SYSTEM_PROMPT, user_prompt)
                raw_steps = self._parse_json_steps(response.raw_text)
                steps = self._normalize_steps([TestStep.model_validate(item) for item in raw_steps])
                steps = self._contextualize_steps(prompt, base_url, workflow_context, steps)
                if not steps:
                    raise PlanningError("Planner returned no executable steps")

                if settings.AI_CACHE_ENABLED:
                    self.db.add(
                        PromptCache(
                            key=cache_key,
                            prompt=prompt,
                            base_url=base_url,
                            provider=response.provider,
                            model=response.model,
                            steps_json=[step.model_dump(mode="json") for step in steps],
                        )
                    )
                    await self.db.commit()

                return steps, {"provider": response.provider, "model": response.model, "cache_hit": False}
            except Exception as exc:  # Provider fallback must be broad by design.
                await self.db.rollback()
                errors.append(f"{provider_name}: {exc}")

        fallback_steps = build_rule_based_plan(prompt, base_url, workflow_context)
        if fallback_steps:
            return fallback_steps, {
                "provider": "deterministic-fallback",
                "model": "rules",
                "cache_hit": False,
                "provider_errors": errors,
            }

        raise PlanningError(
            "No AI provider produced a valid plan. Configure GEMINI_API_KEY or OPENAI_API_KEY. "
            + " | ".join(errors)
        )

    def _parse_json_steps(self, text: str) -> list[dict[str, Any]]:
        cleaned = self._strip_code_fence(text.strip())
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"(\[.*\]|\{.*\})", cleaned, re.DOTALL)
            if not match:
                raise PlanningError(f"Planner response was not JSON: {cleaned[:200]}")
            payload = json.loads(match.group(1))

        if isinstance(payload, dict) and "steps" in payload:
            payload = payload["steps"]
        if not isinstance(payload, list):
            raise PlanningError("Planner JSON must be an array or an object with a steps array")

        return payload

    def _normalize_steps(self, steps: list[TestStep]) -> list[TestStep]:
        normalized: list[TestStep] = []
        skip_next = False
        for index, step in enumerate(steps):
            if skip_next:
                skip_next = False
                continue
            next_step = steps[index + 1] if index + 1 < len(steps) else None
            target = (step.target or "").lower().replace(" ", "_")
            next_target = (next_step.target or "").lower().replace(" ", "_") if next_step else ""
            product_index = self._target_product_index(target)
            if (
                step.action.value == "type"
                and target in {"searchbox", "search_box", "search_input"}
                and next_step
                and next_step.action.value in {"click", "press_key"}
                and ("search" in next_target or next_step.value in {"Enter", "enter"})
            ):
                normalized.append(
                    TestStep(action="search", target="searchbox", value=step.value, timeout_ms=step.timeout_ms)
                )
                skip_next = True
                continue
            if step.action.value == "click" and product_index:
                normalized.append(
                    TestStep(
                        action="open_product",
                        target="product_result",
                        value={"index": product_index},
                        timeout_ms=step.timeout_ms,
                    )
                )
                continue
            if step.action.value == "click" and target in {"add_to_cart", "add_to_cart_button", "cart_button"}:
                normalized.append(
                    TestStep(action="add_to_cart", target="add_to_cart_button", value=step.value, timeout_ms=step.timeout_ms)
                )
                continue
            normalized.append(step)
        return normalized

    @staticmethod
    def _target_product_index(target: str) -> int | None:
        if target in {"first_product", "first_result", "product_result", "product"}:
            return 1
        words = {
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "fifth": 5,
            "sixth": 6,
            "seventh": 7,
            "eighth": 8,
            "ninth": 9,
            "tenth": 10,
        }
        for word, number in words.items():
            if f"{word}_product" in target or f"{word}_result" in target:
                return number
        match = re.search(r"(\d+)(?:st|nd|rd|th)?_(?:product|result)", target)
        if match:
            return int(match.group(1))
        return None

    def _contextualize_steps(
        self,
        prompt: str,
        base_url: str | None,
        workflow_context: str | None,
        steps: list[TestStep],
    ) -> list[TestStep]:
        if not workflow_context or any(step.action.value == "open_url" for step in steps):
            return steps
        text = prompt.lower()
        needs_page_context = any(word in text for word in ["product", "cart", "sort", "filter", "checkout"])
        if not needs_page_context:
            return steps
        contextual_plan = build_rule_based_plan(prompt, base_url, workflow_context)
        if contextual_plan and any(step.action.value == "open_url" for step in contextual_plan):
            return contextual_plan
        return steps

    @staticmethod
    def _should_prefer_specialist_plan(prompt: str, steps: list[TestStep]) -> bool:
        text = prompt.lower()
        if not steps:
            return False
        specialist_actions = {
            "open_product",
            "set_quantity",
            "buy_now",
            "sort_results",
            "filter_results",
            "search_flights",
            "search_hotels",
            "search_cabs",
        }
        if any(step.action.value in specialist_actions for step in steps):
            return True
        return "amazon" in text or "make my trip" in text or "makemytrip" in text

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()
        return text
