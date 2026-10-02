import pytest

from tracker.config import Settings


def settings_con(secret: str, cookie_secure: bool) -> Settings:
    s = Settings()
    s.secret_key = secret
    s.cookie_secure = cookie_secure
    return s


@pytest.mark.parametrize("secret", ["", "dev-inseguro", "corta"])
def test_produccion_rechaza_secret_key_debil(secret):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        settings_con(secret, cookie_secure=True).check_production()


def test_produccion_acepta_secret_key_larga():
    settings_con("x" * 64, cookie_secure=True).check_production()


def test_desarrollo_no_exige_secret_key():
    # COOKIE_SECURE=false es el modo de desarrollo local del README.
    settings_con("", cookie_secure=False).check_production()
