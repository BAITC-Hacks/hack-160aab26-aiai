from app.config import Settings, load_env_file


def test_defaults_point_to_openai_and_have_no_key():
    settings = Settings.from_env({})
    assert settings.llm_base_url == "https://api.openai.com/v1"
    assert settings.llm_api_key == ""
    assert not settings.llm_configured


def test_reads_llm_settings_from_env():
    settings = Settings.from_env(
        {"LLM_API_KEY": " sk-test ", "LLM_BASE_URL": "https://proxy.example/v1/", "LLM_MODEL": "m1"}
    )
    assert settings.llm_api_key == "sk-test"
    assert settings.llm_base_url == "https://proxy.example/v1"
    assert settings.llm_model == "m1"
    assert settings.llm_configured


def test_empty_env_values_fall_back_to_defaults():
    settings = Settings.from_env({"LLM_MODEL": "", "LLM_BASE_URL": ""})
    assert settings.llm_model == Settings().llm_model
    assert settings.llm_base_url == Settings().llm_base_url


def test_env_file_is_loaded_without_overriding_existing_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# комментарий\nLLM_API_KEY='from-file'\nLLM_MODEL=file-model\n\nБЕЗ_РАВНО\n",
        encoding="utf-8",
    )
    env = {"LLM_MODEL": "already-set"}
    load_env_file(env_file, env)
    assert env == {"LLM_MODEL": "already-set", "LLM_API_KEY": "from-file"}


def test_missing_env_file_is_ignored(tmp_path):
    env = {}
    load_env_file(tmp_path / "nope.env", env)
    assert env == {}
