"""ThreadAwareStream routing tests."""

import io
import threading

from drs_host.streams import ThreadAwareStream


def test_registered_thread_routes_to_its_stream():
    fallback = io.StringIO()
    mine = io.StringIO()
    hub = ThreadAwareStream(fallback)
    results = {}

    def worker():
        hub.register(mine)
        print("captured", file=hub)
        hub.flush()
        results["mine"] = mine.getvalue()
        results["fallback"] = fallback.getvalue()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=5)

    assert "captured" in results["mine"]
    assert results["fallback"] == ""


def test_unregistered_thread_uses_fallback():
    fallback = io.StringIO()
    hub = ThreadAwareStream(fallback)
    print("host output", file=hub)
    hub.flush()
    assert "host output" in fallback.getvalue()


def test_unregister_restores_fallback():
    fallback = io.StringIO()
    mine = io.StringIO()
    hub = ThreadAwareStream(fallback)
    hub.register(mine)
    assert hub.registered()
    hub.unregister()
    assert not hub.registered()
    print("after unregister", file=hub)
    assert "after unregister" in fallback.getvalue()
    assert mine.getvalue() == ""


def test_two_threads_are_isolated():
    fallback = io.StringIO()
    stream_a = io.StringIO()
    stream_b = io.StringIO()
    hub = ThreadAwareStream(fallback)
    results = {}

    def worker(tag, stream):
        hub.register(stream)
        print(f"line-{tag}", file=hub)
        hub.flush()
        results[tag] = stream.getvalue()

    threads = [
        threading.Thread(target=worker, args=("a", stream_a)),
        threading.Thread(target=worker, args=("b", stream_b)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert results["a"].strip() == "line-a"
    assert results["b"].strip() == "line-b"
    assert fallback.getvalue() == ""
