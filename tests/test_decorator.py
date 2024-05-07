import os

import pytest
import ray
import responses
import subprocess
from tests.primitives import *


def test_decorator_io():
    _, normal_time = func_basic(2)

    result, dist_time = func_io([1, 2, 3, 4, 5])

    assert normal_time * 1.2 > dist_time
    assert result == [1, 2, 3, 4, 5]


def test_decorator_compute():
    _, normal_time = func_basic(2)

    result, dist_time = func_compute([1, 2, 3, 4, 5])

    assert normal_time * 1.2 > dist_time
    assert result == [1, 2, 3, 4, 5]


@responses.activate
def test_decorator_web():

    def callback(req):
        payload = json.loads(req.body)
        return payload["x"], {"_": ""}, json.dumps(payload["x"])

    responses.add_callback(responses.POST,
                           "https://httpswebpage.org/post", callback=callback)

    _, normal_time = func_basic(2)

    result, dist_time = func_web(range(10), url="https://httpswebpage.org/post")

    assert normal_time * 1.2 > dist_time
    assert result == [i for i in range(10)]


def test_decorator_io_iter():
    _, normal_time = func_basic_iter([i for i in range(1500)])

    result, dist_time = func_io_iter([i for i in range(1500)])

    assert normal_time > dist_time
    assert sum(result) == 1500


def test_decorator_compute_iter():
    _, normal_time = func_basic_iter([i for i in range(1500)])

    result, dist_time = func_compute_iter([i for i in range(1500)])

    assert normal_time > dist_time
    assert sum(result) == 1500


def test_decorator_ray():
    subprocess.run(["ray", "start", "--head", "--port=8080", "--num-cpus=8", "--disable-usage-stats"])
    sleep(1)
    os.environ["RAY_ADDRESS"] = "localhost:8080"

    _, normal_time = func_basic(2)

    result, dist_time = func_ray([1, 2, 3, 4, 5])

    ray.shutdown()
    del os.environ["RAY_ADDRESS"]

    subprocess.run(["ray", "stop"])

    assert normal_time * 1.2 > dist_time
    assert result == [1, 2, 3, 4, 5]


def test_decorator_ray_faulty():
    subprocess.run(["ray", "start", "--head", "--port=8080", "--num-cpus=8", "--disable-usage-stats"])
    sleep(1)
    # os.environ["RAY_ADDRESS"] = "localhost:8080"

    with pytest.raises(KeyError):
        func_ray([1, 2, 3, 4, 5])

    subprocess.run(["ray", "stop"])


