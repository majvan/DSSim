from dssim.lite.components.litequeue import LiteQueue, SimLiteQueueMixin
from dssim.lite.components.literesource import (
    DSResourcePreempted,
    LitePriorityResource,
    LiteResource,
    SimLiteResourceMixin,
)

__all__ = [
    'DSResourcePreempted',
    'LiteQueue',
    'SimLiteQueueMixin',
    'LiteResource',
    'LitePriorityResource',
    'SimLiteResourceMixin',
    'SimLiteProcessMixin',
    'DSLiteProcess',
    'DSLiteAgent',
    'PCLiteGenerator',
]


def __getattr__(name: str):
    if name in ('DSLiteAgent', 'PCLiteGenerator'):
        from dssim.lite.agent import DSLiteAgent, PCLiteGenerator
        return {'DSLiteAgent': DSLiteAgent, 'PCLiteGenerator': PCLiteGenerator}[name]
    if name == 'DSLiteProcess':
        from dssim.lite.process import DSLiteProcess
        return DSLiteProcess
    if name == 'SimLiteProcessMixin':
        from dssim.lite.process import SimLiteProcessMixin
        return SimLiteProcessMixin
    raise AttributeError(f"module 'dssim.lite' has no attribute '{name}'")
