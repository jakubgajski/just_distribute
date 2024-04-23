import inspect
from concurrent.futures import ThreadPoolExecutor
import asyncio
from inspect import signature
from functools import wraps, partial
from typing import Callable
from collections.abc import Collection, Iterable
import itertools as it

from psutil import cpu_count, cpu_percent
from pathos.multiprocessing import ProcessPool


def batched(iterable, n):
    """
    From itertools -> just not available below Python 3.12
    """
    # batched('ABCDEFG', 3) → ABC DEF G
    if n < 1:
        raise ValueError('n must be at least one')
    itera = iter(iterable)
    while batch := tuple(it.islice(itera, n)):
        yield batch


def make_func_async(func: Callable):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


async def consumer(queue: asyncio.Queue, func: Callable) -> list:
    """
    Consumer to use only within consume_queue. Just calls passed on items from the queue.

    Parameters
    ----------
    queue: asyncio.Queue
    func: Callable

    Returns
    -------
    A list of responses from the coroutine function (that if called with consumer means that
    the function calls something over the web :)).
    """
    responses = []
    while True:
        try:
            item, idx = queue.get_nowait()
        except asyncio.queues.QueueEmpty:
            break
        response = await func(item)
        responses.append((response, idx))
        queue.task_done()
    return responses


async def consume_queue(queue: asyncio.Queue, func: Callable, workers: int) -> list:
    """
    Consume the queue with workers * func consumers.

    Parameters
    ----------
    queue: asyncio.Queue
    func: Callable
    workers: int

    Returns
    -------
    A flattened list aggregated across all consumers
    """
    consumers = [asyncio.create_task(consumer(queue, func)) for _ in range(workers)]
    results = await asyncio.gather(*consumers)
    await queue.join()
    results = [(item, idx) for sublist in results for item, idx in sublist]
    return [item for item, idx in sorted(results, key=lambda x: x[1])]


def distribute(job: str = "compute", workers: int = None):
    """
    Distributes function that process arbitrary object across chosen worker types.
    Essentially making it a function that process a sequence of objects in parallel.

    Parameters
    ----------
    job: str
        Type of job to be distributed. Can be 'compute' aka 'processes', 'io' aka 'threads' or 'web' aka 'coroutines'.
        'compute' leverages processes, 'io' leverages threads, 'web' leverages coroutines.
    workers: int
        Number of workers to be used. If None, the number of workers equals to the number of half available threads
        on the machine, regardless of the job type.

    Returns
    -------
    Callable

    Examples
    --------
    >>> @distribute(job='compute', workers=4)
    >>> def func(x: int, operation: str = 'sub'):
    >>>     if operation == 'add':
    >>>         return x + 1
    >>>     else:
    >>>         return x - 1

    >>> func([1, 2, 3, 4, 5], operation='add')
    [2, 3, 4, 5, 6]
    """
    if workers is None:
        # half o available compute expressed in threads
        _workers = (((100 - cpu_percent(1)) / 100) * cpu_count() / 2) // 1
    else:
        _workers = workers

    def decorator(func: Callable):

        # if first argument is by default Collection or Iterable, new argument must be batched
        first_arg_annotation = next(iter(signature(func).parameters.values())).annotation

        if first_arg_annotation is inspect.Parameter.empty:
            raise TypeError(f"Function {func} first argument has to be annotated with typehint.")

        is_first_arg_collection = issubclass(
            first_arg_annotation, (Collection, Iterable)
        )

        @wraps(func)
        def wrapper(to_distribute: Collection | Iterable, **kwargs):

            if kwargs:
                part_func = partial(func, **kwargs)
            else:
                part_func = func

            if is_first_arg_collection:
                to_distribute = list(batched(to_distribute, cpu_count() * 2))

            if not isinstance(to_distribute, (Collection, Iterable)):
                raise TypeError(f"Object {to_distribute} is neither a collection nor an iterable.")

            if job in ("compute", "processes"):
                with ProcessPool(nodes=_workers) as executor:
                    return list(executor.map(part_func, to_distribute, chunksize=len(to_distribute) // _workers))
            elif job in ("io", "threads"):
                with ThreadPoolExecutor(max_workers=_workers) as executor:
                    return list(executor.map(part_func, to_distribute))
            elif job in ("web", "coroutines"):
                # assuming we have known amount of consumers, e.g. orchestrated via Nomad or Kubernetes
                # we should feed them simultaneously although asynchronously
                if not asyncio.iscoroutinefunction(part_func):
                    part_func = make_func_async(part_func)

                queue = asyncio.Queue()
                for idx, item in enumerate(to_distribute):
                    queue.put_nowait((item, idx))

                return asyncio.run(consume_queue(queue, part_func, _workers))

        return wrapper

    return decorator
