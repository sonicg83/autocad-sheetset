import threading
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from dst_manager.application.cad_job import CadJobRunner, RebuildResult, RebuildWorkUnit
from dst_manager.config import Settings
from dst_manager.infrastructure.autocad.worker import CadCapability
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.filesystem.publisher import RecoverablePublisher


class FakeDatabase:
    def update_job(self, *_args, **_kwargs):
        return None

    def heartbeat(self, *_args, **_kwargs):
        return True


def _unit(tmp_path: Path, index: int) -> RebuildWorkUnit:
    return RebuildWorkUnit(index, {}, tmp_path / "source.dwg", tmp_path, tmp_path, tmp_path, 10)


def test_parallel_setting_defaults_to_two_and_rejects_out_of_range(tmp_path: Path):
    assert Settings(data_dir=tmp_path).cad_max_parallel == 2
    for value in (0, 5):
        with pytest.raises(ValidationError):
            Settings(data_dir=tmp_path, cad_max_parallel=value)


@pytest.mark.parametrize(("parallel", "expected"), [(1, 1), (2, 2), (4, 4)])
def test_group_scheduler_is_bounded(tmp_path: Path, parallel: int, expected: int):
    runner = CadJobRunner(FakeDatabase(), DstCodec(), RecoverablePublisher(), 10, parallel)
    active = 0
    maximum = 0
    lock = threading.Lock()

    def rebuild(_job, _workspace, _capability, unit):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        target = tmp_path / f"{unit.index}.dwg"
        return RebuildResult(unit.index, target, target, target, {}, 30, tmp_path / "x.log", 100, 200)

    runner._rebuild_group = rebuild
    results = runner._run_groups("job", "worker", object(), CadCapability("2020", None, None), [_unit(tmp_path, index) for index in range(6)])
    assert [item.index for item in sorted(results, key=lambda item: item.index)] == list(range(6))
    assert maximum == min(expected, 6)


def test_failure_stops_submitting_new_groups(tmp_path: Path):
    runner = CadJobRunner(FakeDatabase(), DstCodec(), RecoverablePublisher(), 10, 2)
    started = []

    def rebuild(_job, _workspace, _capability, unit):
        started.append(unit.index)
        if unit.index == 0:
            raise RuntimeError("boom")
        time.sleep(0.05)
        target = tmp_path / f"{unit.index}.dwg"
        return RebuildResult(unit.index, target, target, target, {}, 50, tmp_path / "x.log", 100, 200)

    runner._rebuild_group = rebuild
    with pytest.raises(RuntimeError, match="boom"):
        runner._run_groups("job", "worker", object(), CadCapability("2020", None, None), [_unit(tmp_path, index) for index in range(5)])
    assert set(started) <= {0, 1}
