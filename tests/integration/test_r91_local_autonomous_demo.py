from demos.r91_autonomous_boundary import DEMO_TOKEN, run_demo


def test_r91_local_autonomous_boundary_demo(tmp_path):
    assert run_demo(tmp_path / "workspace") == DEMO_TOKEN
