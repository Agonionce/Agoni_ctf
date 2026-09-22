from demos.r101_experiment_runtime import DEMO_TOKEN, run_demo


def test_local_experiment_runtime(tmp_path):
    assert run_demo(tmp_path) == DEMO_TOKEN
