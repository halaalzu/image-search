# plugins/healthbar_bus.py
from collections import deque
from threading import Lock
from time import time_ns

_queue = deque()
_lock  = Lock()

def post_event(kind, source=None, value=None):
    """
    kind: 'HIT' | 'MISS' | 'FA' | 'CORRECT' | 'BAD_FREQ' | 'BAD_RADIO' | ...
    source: optional plugin name, e.g. 'sysmon' or 'communications'
    value: optional numeric payload
    """
    with _lock:
        _queue.append((time_ns(), kind, source, value))

def drain_events(max_items=128):
    out = []
    with _lock:
        for _ in range(min(max_items, len(_queue))):
            out.append(_queue.popleft())
    return out
