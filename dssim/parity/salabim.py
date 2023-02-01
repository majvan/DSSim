from dssim.simulation import DSSimulation, DSComponent as component, DSSchedulable, DSProcess, DSCallback, DSAbsTime, DSAbortException
from dssim.pubsub import DSProducer
from dssim.cond import DSFilter
from dssim.processcomponent import DSProcessComponent as Component

from dssim.components.queue import Queue
from dssim.components.resource import Resource
from dssim.components.state import State

class Environment(DSSimulation):
    def now(self):
        return self.time
