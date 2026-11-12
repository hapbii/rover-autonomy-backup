import importlib
import tracemalloc
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest


def demo_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("run_demo")


def test_demo_initialization_failure_closes_model(monkeypatch, tmp_path):
    demo = demo_module(monkeypatch)

    class Palm:
        closed = False

        def __init__(self, _):
            pass

        def close(self):
            Palm.closed = True

    monkeypatch.setattr(demo, "PalmDetector", Palm)

    def failed_read(_):
        raise ValueError("missing reference image")

    monkeypatch.setattr(demo, "read_image", failed_read)
    with pytest.raises(ValueError, match="reference"):
        demo.run_case("hand_follow", tmp_path)
    assert Palm.closed


@pytest.mark.parametrize("opened", [False, True])
def test_demo_writer_and_temp_file_are_released_on_failure(monkeypatch, tmp_path, opened):
    demo = demo_module(monkeypatch)
    temporary_file = tmp_path / "incomplete.mp4"
    mkstemp = demo.tempfile.mkstemp
    writer_closed = []

    def create_temp(**_):
        handle, name = mkstemp(dir=tmp_path, suffix=".mp4")
        nonlocal temporary_file
        temporary_file = Path(name)
        return handle, name

    class Writer:
        def __init__(self, *_):
            pass

        def isOpened(self):
            return opened

        def release(self):
            writer_closed.append(True)

    def failed_process(*_, **__):
        raise RuntimeError("injected frame failure")

    monkeypatch.setattr(demo.tempfile, "mkstemp", create_temp)
    monkeypatch.setattr(demo.cv2, "VideoWriter", Writer)
    monkeypatch.setattr(demo.PerceptionPipeline, "process", failed_process)
    with pytest.raises(RuntimeError):
        demo.run_case("line_follow", tmp_path)
    assert writer_closed == [True]
    assert not temporary_file.exists()


def test_soak_close_failure_still_releases_native_model_and_tracing(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    soak = importlib.import_module("memory_soak")
    original_pipeline = soak.PerceptionPipeline
    instances = []

    class Pipeline(original_pipeline):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            instances.append(self)

        def process(self, *_):
            raise RuntimeError("injected processing failure")

    def bad_close(_):
        raise OSError("injected serial close failure")

    monkeypatch.setattr(soak, "PerceptionPipeline", Pipeline)
    monkeypatch.setattr(soak.BoundedWire, "close", bad_close)
    args = SimpleNamespace(frames=1000, warmup=128, hand_stride=8, output=tmp_path / "unused.json")
    with pytest.raises(OSError, match="serial close"):
        with ExitStack() as resources:
            soak.run(args, resources)
    assert instances[0].closed and instances[0].palm is None
    assert not tracemalloc.is_tracing()
