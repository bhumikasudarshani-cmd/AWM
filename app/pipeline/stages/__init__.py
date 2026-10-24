from app.config import settings
from app.pipeline.base import Stage
from app.pipeline.stages.rules import RulesStage


def default_stages() -> list[Stage]:
    stages: list[Stage] = [RulesStage()]
    if settings.llm_base_url and settings.llm_model:
        from app.llm.openai_compat import OpenAICompatProvider
        from app.pipeline.stages.security_llm import LLMSecurityStage

        provider = OpenAICompatProvider(
            settings.llm_base_url, settings.llm_model, settings.llm_api_key, timeout=settings.llm_timeout
        )
        stages.append(LLMSecurityStage(
            provider,
            max_input_tokens=settings.llm_max_input_tokens,
            max_calls=settings.llm_max_calls,
            timeout=settings.llm_timeout + 60,
        ))
    return stages