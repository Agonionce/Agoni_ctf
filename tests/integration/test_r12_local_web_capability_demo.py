from demos.r12_web_capability_evolution import main


def test_r12_fake_local_web_capability_demo(capsys):
    main()
    assert "LOCAL_WEB_CAPABILITY_EVOLUTION_OK" in capsys.readouterr().out
