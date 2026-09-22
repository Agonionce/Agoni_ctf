from demos.r11_web_autonomous_research import (
    DEMO_TOKEN,
    run_demo,
)


def test_r11_fake_local_web_autonomous_research(tmp_path):
    assert run_demo(tmp_path) == DEMO_TOKEN
