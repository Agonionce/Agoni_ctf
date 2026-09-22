from demos.r8_local_web_intelligence_loop import DEMO_TOKEN, run_demo


def test_r8_local_web_intelligence_loop(tmp_path):
    assert run_demo(tmp_path / "workspace") == DEMO_TOKEN
