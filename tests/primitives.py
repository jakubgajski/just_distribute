import json
from collections.abc import Iterable

import requests
import asyncio

from functools import wraps
from time import time, sleep

from just_distribute import distribute


SLEEP = 2

def timing(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time()
        res = func(*args, **kwargs)
        return res, time() - start

    return wrapper


@timing
def func_basic(x: int):
    sleep(SLEEP)
    return x


@timing
@distribute(job="io", workers=5)
def func_io(x: int, y: int):
    sleep(SLEEP)
    return x + y


@timing
@distribute(job="compute", workers=5)
def func_compute(x: int, y: int):
    sleep(SLEEP)
    return x + y


@timing
@distribute(job="web", workers=10)
async def func_web(x: int, y: int, *, url: str):
    response = requests.post(url, json.dumps({"x": x + y}))
    await asyncio.sleep(SLEEP)
    return response.status_code


@timing
def func_basic_iter(x: Iterable):
    counter = 0
    for _ in x:
        counter += 1
        sleep(SLEEP / 1000)
    return counter


@timing
@distribute(job="io", workers=8)
def func_io_iter(x: Iterable, y: Iterable):
    counter = 0
    for _ in x:
        counter += 1
        sleep(SLEEP / 1000)
    return counter, sum(map(lambda a, b: a + b, x, y))


@timing
@distribute(job="compute", workers=8)
def func_compute_iter(x: Iterable, y: Iterable):
    counter = 0
    for _ in x:
        counter += 1
        sleep(SLEEP / 1000)
    return counter, sum(map(lambda a, b: a + b, x, y))


@timing
@distribute(job="ray")
def func_ray(x: int, y: int):
    sleep(SLEEP)
    return x + y


@timing
@distribute(job="ray")
def func_ray_iter(x: Iterable, y: Iterable):
    counter = 0
    for _ in x:
        counter += 1
        sleep(SLEEP / 1000)
    return counter, sum(map(lambda a, b: a + b, x, y))
