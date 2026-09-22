from demos.r102_autonomous_experiment_loop import DEMO_TOKEN, run_demo


def test_r102_fake_local_autonomous_experiment_loop(tmp_path):
    assert run_demo(tmp_path) == DEMO_TOKEN
