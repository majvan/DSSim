from dssim.lite.pubsub import DSLiteCallback, DSLitePub, DSLiteSub, SimLitePubsubMixin
from dssim.lite.components.litequeue import DSLiteQueue, SimLiteQueueMixin
from dssim.lite.components.literesource import (
    DSResourcePreempted,
    DSLitePriorityResource,
    DSLiteResource,
    DSLiteUnitResource,
    SimLiteResourceMixin,
)
from dssim.lite.components.litetime import (
    DSLiteDelay,
    DSLiteLimiter,
    DSLiteTimer,
    SimLiteTimeMixin,
)

__all__ = [
    'DSResourcePreempted',
    'DSLiteCallback',
    'DSLitePub',
    'DSLiteSub',
    'SimLitePubsubMixin',
    'DSLiteDelay',
    'DSLiteLimiter',
    'DSLiteQueue',
    'DSLiteTimer',
    'SimLiteQueueMixin',
    'DSLiteResource',
    'DSLiteUnitResource',
    'DSLitePriorityResource',
    'SimLiteResourceMixin',
    'SimLiteTimeMixin',
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
