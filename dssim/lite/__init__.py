from dssim.lite.components.litequeue import LiteQueue, SimLiteQueueMixin
from dssim.lite.components.literesource import (
    LitePriorityResource,
    LiteResource,
    SimLiteResourceMixin,
)

__all__ = [
    'LiteQueue',
    'SimLiteQueueMixin',
    'LiteResource',
    'LitePriorityResource',
    'SimLiteResourceMixin',
    'DSLiteAgent',
    'PCLiteGenerator',
]


def __getattr__(name: str):
    if name in ('DSLiteAgent', 'PCLiteGenerator'):
        from dssim.lite.agent import DSLiteAgent, PCLiteGenerator
        return {'DSLiteAgent': DSLiteAgent, 'PCLiteGenerator': PCLiteGenerator}[name]
    raise AttributeError(f"module 'dssim.lite' has no attribute '{name}'")
