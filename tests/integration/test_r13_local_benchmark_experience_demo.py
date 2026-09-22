from demos.r13_web_benchmark_experience import main


def test_r13_fake_local_benchmark_experience_demo(capsys):
    main()
    assert "LOCAL_WEB_BENCHMARK_EXPERIENCE_EVOLUTION_OK" in capsys.readouterr().out
