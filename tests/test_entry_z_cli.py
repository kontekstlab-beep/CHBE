"""CLI-флаг --entry-z: переопределение порога входа для спарринг-бота."""
import run_paper


def _run_main(monkeypatch, tmp_path, argv):
    # пути — модульные константы, читаются из env при импорте; переопределяем напрямую
    monkeypatch.setattr(run_paper, "STATE_PATH", str(tmp_path / "st.json"))
    monkeypatch.setattr(run_paper, "LOG_PATH", str(tmp_path / "lg.log"))
    monkeypatch.setattr("sys.argv", argv)
    captured = {}
    monkeypatch.setattr(run_paper, "run_once", lambda cfg: captured.update(z=cfg.entry_z))
    run_paper.main()
    return captured


def test_entry_z_override(monkeypatch, tmp_path):
    assert _run_main(monkeypatch, tmp_path, ["run_paper.py", "--entry-z", "-1.5"])["z"] == -1.5


def test_entry_z_default_frozen(monkeypatch, tmp_path):
    assert _run_main(monkeypatch, tmp_path, ["run_paper.py"])["z"] == -2.0
