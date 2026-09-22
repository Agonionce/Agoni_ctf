from demos.r86_local_completion_pipeline import main


def test_r86_local_completion_pipeline_demo(capsys):
    main()

    assert "LOCAL_COMPLETION_PIPELINE_OK" in capsys.readouterr().out
