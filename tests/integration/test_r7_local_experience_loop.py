"""R7 local cross-challenge experience creation and retrieval demo."""

from demos.r7_local_experience_loop import (
    CREATE_TOKEN,
    LOOP_TOKEN,
    RETRIEVE_TOKEN,
    run_demo,
)


def test_local_experience_loop(tmp_path):
    assert run_demo(tmp_path) == (CREATE_TOKEN, RETRIEVE_TOKEN, LOOP_TOKEN)
