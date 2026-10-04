"""One cancellable worker and a main-thread completion queue."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from contextlib import contextmanager
from queue import Queue, Empty
import threading
import logging

_cancel = ContextVar('cancel_job', default=None)

class CancelledError(Exception):
    pass

def check_cancelled():
    event = _cancel.get()
    if event is not None and event.is_set():
        raise CancelledError('Operation cancelled')

@contextmanager
def cancellation(event):
    token = _cancel.set(event)
    try:
        yield
    finally:
        _cancel.reset(token)

class JobRunner:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='gemba')
        self.messages = Queue()
        self.cancel_event = threading.Event()
        self.busy = False

    def submit(self, work, done, failed):
        if self.busy:
            raise RuntimeError('A job is already running. Cancel it or wait for completion.')
        self.busy = True
        self.cancel_event.clear()
        def run():
            try:
                with cancellation(self.cancel_event):
                    result = work()
                    check_cancelled()
                self.messages.put((done, result))
            except CancelledError as exc:
                self.messages.put((failed, str(exc)))
            except Exception as exc:
                logging.getLogger(__name__).exception('Background job failed')
                self.messages.put((failed, str(exc)))
        self.executor.submit(run)

    def poll(self):
        try:
            callback, value = self.messages.get_nowait()
        except Empty:
            return
        self.busy = False
        callback(value)

    def cancel(self):
        self.cancel_event.set()

    def close(self):
        self.cancel()
        self.executor.shutdown(wait=False, cancel_futures=True)
