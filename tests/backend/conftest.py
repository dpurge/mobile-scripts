import json
import time
import urllib.error
import urllib.request

import pytest


@pytest.fixture
def call():
    """`call(method, url, body=None, content_type=...)` -> (status, parsed JSON body)."""

    def _call(method, url, body=None, content_type="application/json", raw=None):
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        request = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    return _call


@pytest.fixture
def wait_until():
    """`wait_until(predicate, seconds=10)` polls and fails the test on timeout."""

    def _wait(predicate, seconds=10.0):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        pytest.fail(f"condition not met within {seconds} s")

    return _wait
