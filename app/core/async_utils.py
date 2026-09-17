import asyncio
import threading

_worker_loop = None


def get_worker_loop():
    global _worker_loop
    if _worker_loop is None:
        _worker_loop = asyncio.new_event_loop()

        def _run_loop(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()

        t = threading.Thread(target=_run_loop, args=(_worker_loop,), daemon=True)
        t.start()
    return _worker_loop


def run_async(coro):
    loop = get_worker_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop).result()
