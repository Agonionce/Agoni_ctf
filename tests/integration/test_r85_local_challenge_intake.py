from demos.r85_local_challenge_intake import main


def test_r85_local_challenge_intake_demo(capsys):
    main()

    assert "LOCAL_CHALLENGE_INTAKE_OK" in capsys.readouterr().out
