from demos.r14_local_ui_workbench import main


def test_r14_local_ui_workbench_demo(capsys):
    main()

    assert "LOCAL_UI_WORKBENCH_OK" in capsys.readouterr().out
