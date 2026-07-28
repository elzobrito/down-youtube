"""Runtime stats helpers for the general stats panel."""

from utils.runtime_stats import (
    dir_delta_mb,
    path_size_mb,
    process_cpu_percent,
    process_thread_count,
)


def test_process_thread_count_positive():
    n = process_thread_count()
    assert isinstance(n, int)
    assert n >= 1


def test_process_cpu_percent_is_float_range():
    # First call may be 0 (baseline); second after a bit of work is still float
    a = process_cpu_percent()
    _ = sum(range(100000))
    b = process_cpu_percent()
    assert isinstance(a, float)
    assert isinstance(b, float)
    assert 0.0 <= a <= 100.0
    assert 0.0 <= b <= 100.0


def test_path_and_delta_mb(tmp_path):
    f = tmp_path / "blob.bin"
    f.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MiB
    size = path_size_mb(str(f))
    assert 1.9 <= size <= 2.1
    base = path_size_mb(str(tmp_path))
    f2 = tmp_path / "more.bin"
    f2.write_bytes(b"y" * (1024 * 1024))
    delta = dir_delta_mb(str(tmp_path), base - 0.01)
    assert delta >= 0.9
