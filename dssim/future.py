from contextlib import contextmanager
import inspect
from dssim.base import SignalMixin, DSAbortException, TrackEvent
from dssim.pubsub import _ConsumerMetadata, DSConsumer, DSProducer


class DSFuture(DSConsumer, SignalMixin):
    ''' Typical future which can be used in the simulations.
    This represents a base for all awaitables.
    '''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We store the latest value or excpetion. Useful to check the status after finish.
        self.value, self.exc = None, None
        self._finish_tx = DSProducer(name=self.name+'.future', sim=self.sim)
    
    def create_metadata(self, **kwargs):
        self.meta = _ConsumerMetadata()
        self.meta.cond.push(self)  # sending to self => signaling the end of future
        return self.meta

    def get_future_eps(self):
        return {self._finish_tx,}

    def finished(self):
        return (self.value, self.exc) != (None, None)

    def abort(self, exc=None):
        ''' Aborts an awaitable with an exception. '''
        if exc is None:
            exc = DSAbortException(self)
        try:
            self.sim.try_send(self, exc)
        except StopIteration as e:
            self.finish(e)
        except Exception as e:
            self.fail(e)

    def gwait(self, timeout=float('inf')):
        retval = None
        if not self.finished():
            with self.sim.observe_pre(self):
                retval = yield from self.sim.gwait(timeout, cond=self)
        if self.exc is not None:
            raise self.exc
        return retval

    async def wait(self, timeout=float('inf')):
        retval = None
        if not self.finished():
            with self.sim.observe_pre(self):
                retval = await self.sim.wait(timeout, cond=self)
        if self.exc is not None:
            raise self.exc
        return retval

    def __await__(self):
        retval = yield from self.gwait()
        return retval

    def finish(self, value):
        self.value = value
        self.sim.cleanup(self)
        self._finish_tx.signal(self)
    
    def fail(self, exc):
        self.exc = exc
        self.sim.cleanup(self)
        self._finish_tx.signal(self)

    @TrackEvent
    def send(self, event):
        self.finish(event)
        return event
