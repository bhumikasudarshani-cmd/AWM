from app.pipeline.base import Stage
from app.pipeline.stages.rules import RulesStage


def default_stages() -> list[Stage]:
    return [RulesStage()]
