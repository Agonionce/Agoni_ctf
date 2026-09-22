"""R6 fake local Web experiment demo; no external target or real exploit."""

from demos.r6_local_experiment_loop import DEMO_TOKEN, run_demo


def test_local_experiment_loop(tmp_path):
    assert run_demo(tmp_path / "workspace") == DEMO_TOKEN
