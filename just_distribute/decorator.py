import asyncio
import inspect
import os
from collections.abc import Collection, Iterable
from concurrent.futures import ThreadPoolExecutor
from functools import wraps, partial
from inspect import signature
from typing import Callable, Literal

import itertools as it
import ray
from pathos.multiprocessing import ProcessPool
from psutil import cpu_count, cpu_percent


# job types names supported by the @distribute decorator
JobTypes = Literal["compute", "io", "web", "ray", "cluster", "threads", "coroutines", "processes"]


def unpack_arguments_tuple(func: Callable) -> Callable:
    """
    Helper decorator to unpack arguments passed to the function.

    Parameters
    ----------
    func: Callable

    Returns
    -------
    Callable
    """

    def wrapper(pack: Collection):
        return func(*pack)

    return wrapper


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


def alter_args_signature(func: Callable) -> Callable:
    """
    Alters the signature of a function if args are non-iterable, non-collection primitives
    into a list[ArgType].

    Parameters
    ----------
    func: Callable

    Returns
    -------
    Callable
    """
    old_signature = inspect.signature(func)
    old_signature_list = list(old_signature.parameters.values())

    altered = []
    for param in old_signature_list:
        if param.kind == inspect.Parameter.VAR_POSITIONAL and not issubclass(param.annotation, Iterable):
            new_param = inspect.Parameter(param.name, inspect.Parameter.VAR_POSITIONAL,
                                          annotation=list[param.annotation])
            altered.append(new_param)

    new_signature_list = altered + old_signature_list[len(altered):]
    new_signature = inspect.Signature(parameters=new_signature_list)

    func.__signature__ = new_signature
    return func


def execute_web_type_workload(args, workers, func: Callable):
    """
    Execute web-type workload asynchronously with consumers and queue

    Parameters
    ----------
    args: list
    workers: int
    func: Callable

    Returns
    -------
    A flattened list aggregated across all consumers.
    """
    if not asyncio.iscoroutinefunction(func):
        func = make_func_async(func)

    queue = asyncio.Queue()
    for idx, items in enumerate(zip(*args)):
        queue.put_nowait((*items, idx))

    return asyncio.run(consume_queue(queue, func, workers))


def execute_ray_type_workload(args, func: Callable):
    """
    Execute workload on prepared ray cluster.

    Parameters
    ----------
    args: list
    func: Callable

    Returns
    -------
    A flat list.
    """
    if not ray.is_initialized():
        try:
            ray.init(
                os.environ["RAY_ADDRESS"], namespace="just_distribute"
            )
        except KeyError:
            raise KeyError("just_distribure expects RAY_ADDRESS environment variable to be set and"
                           " containing the address of a functioning and configured Ray cluster.")

    wrapped_func = unpack_arguments_tuple(func)
    ray_func = ray.remote(wrapped_func)
    ray_data = [ray.put(elem) for elem in zip(*args)]
    return ray.get([ray_func.remote(ref) for ref in ray_data])


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
            *items, idx = queue.get_nowait()
        except asyncio.queues.QueueEmpty:
            break
        response = await func(*items)
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


def distribute(job: JobTypes = "compute",
               workers: int = None, autobatch: bool = True) -> Callable:
    """
    Distributes function that process arbitrary object across chosen worker types.
    Essentially making it a function that process a sequence of objects in parallel.

    Parameters
    ----------
    job: str
        Type of job to be distributed. Can be 'compute' aka 'processes', 'io' aka 'threads', 'web' aka 'coroutines'
        or 'ray' aka 'cluster'.
        'compute' leverages processes, 'io' leverages threads, 'web' leverages coroutines, 'ray' leverages ray cluster.
    workers: int
        Number of workers to be used. If None, the number of workers equals to the number of half available threads
        on the machine, regardless of the job type. Ignored for job='ray'.
    autobatch: bool
        If True and wrapped function takes an Iterable[Something] as an argument(s) of interest, decorator assumes that
        user will pass just (possibly longer) Iterable[Something] of and not an Iterable[Iterable[Something]].
        In case of an Iterable[Something], the decorator will batch the input automatically into
        an Iterable[Iterable[Something]] to distribute sub-iterables across workers. User can of course set autobatch
        to False and provide prepared Iterable[Iterable[Something]] manually, but equal length of all arguments
        of interest must be preserved.

    Returns
    -------
    Callable

    Examples
    --------
    ```python
    >>> @distribute(job='compute', workers=4)
    >>> def func(x: int, operation: str = 'sub'):
    >>>      if operation == 'add':
    >>>          return x + 1
    >>>      else:
    >>>          return x - 1

    >>> func([1, 2, 3, 4, 5], operation='add')
    [2, 3, 4, 5, 6]
    ```
    """
    if workers is None:
        # a half of available compute expressed in threads
        _workers = int((((100 - cpu_percent(1)) / 100) * cpu_count() / 2) // 1)
    else:
        _workers = workers

    def decorator(func: Callable):
        func_params = signature(func).parameters
        func_params_vals = list(func_params.values())
        func_params_kinds = {param.name: param.kind for param in func_params_vals}

        if any([param.annotation is inspect.Parameter.empty for param in func_params_vals]):
            raise TypeError(f"Function {func} must be annotated with typehints.")

        @wraps(func)
        def wrapper(*args: Collection | Iterable, **kwargs):

            if kwargs:
                part_func = partial(func, **kwargs)
            else:
                part_func = func

            used_args = [name for name in func_params_kinds if name not in kwargs]
            args_lengths = len(set(len(arg) for arg in args))

            if autobatch and all(
                    [issubclass(func_params[name].annotation, Iterable) for name in used_args]
            ) and args_lengths == 1:
                args = [list(batched(args[i], _workers * 2)) for i in range(len(args))]

            elif autobatch and any(
                    [not issubclass(func_params[name].annotation, Iterable) for name in used_args]
            ) and args_lengths != 1:
                # some need to be batched and others not (weren't Iterables in the wrapped function)
                min_length = min([len(arg) for arg in args])
                max_length = max([len(arg) for arg in args])

                if max_length % min_length != 0:
                    raise ValueError(f"Passed arguments' lengths are incompatible thus autobatch is not possible. "
                                     f"Tried to autobatch for arguments with lengths {[len(arg) for arg in args]}.")

                args = [list(batched(arg, len(arg) // min_length)) for arg in args]

            elif not autobatch and args_lengths != 1:
                raise ValueError(f"Passed arguments' lengths are incompatible."
                                 f"Tried to distribute workload for arguments with "
                                 f" lengths {[len(arg) for arg in args]}.")

            if not all([isinstance(arg, Iterable) for arg in args]):
                raise TypeError(f"Among objects {[arg for arg in args]} some are neither a collection nor an iterable.")

            if job in ("compute", "processes"):
                with ProcessPool(nodes=_workers) as executor:
                    return list(executor.map(part_func, *args, chunksize=len(args[0]) // _workers))

            elif job in ("io", "threads"):
                with ThreadPoolExecutor(max_workers=_workers) as executor:
                    return list(executor.map(part_func, *args))

            elif job in ("web", "coroutines"):
                # assuming we have known amount of consumers, e.g. orchestrated via Nomad or Kubernetes
                # we should feed them simultaneously although asynchronously
                return execute_web_type_workload(args, _workers, part_func)

            elif job in ("ray", "cluster"):
                return execute_ray_type_workload(args, part_func)

        return alter_args_signature(wrapper)

    return decorator
