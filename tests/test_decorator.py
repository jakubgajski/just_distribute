import responses
from tests.primitives import *


def test_decorator_io():
    _, normal_time = func_basic(1)

    result, dist_time = func_io([1, 2, 3, 4, 5])

    assert normal_time * 2 > dist_time
    assert result == [1, 2, 3, 4, 5]


def test_decorator_compute():
    _, normal_time = func_basic(1)

    result, dist_time = func_compute([1, 2, 3, 4, 5])

    assert normal_time * 2 > dist_time
    assert result == [1, 2, 3, 4, 5]


@responses.activate
def test_decorator_web():

    def callback(req):
        payload = json.loads(req.body)
        return payload["x"], {"_": ""}, json.dumps(payload["x"])

    responses.add_callback(responses.POST,
                           "https://httpswebpage.org/post", callback=callback)

    _, normal_time = func_basic(1)

    result, dist_time = func_web([1, 2, 3, 4, 5], url="https://httpswebpage.org/post")

    assert normal_time * 2 > dist_time
    assert result == [1, 2, 3, 4, 5]


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
