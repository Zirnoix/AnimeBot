"""Tests du module i18n et des fichiers JSON de locale."""
from __future__ import annotations

import pytest

from modules import i18n


@pytest.fixture(autouse=True)
def _reload_locales():
    i18n.reload_locales()
    yield
    i18n.reload_locales()


def test_t_basic_fr():
    s = i18n.t("language.lang_name_fr", "fr")
    assert s == "français"
    assert "français" in s or s


def test_t_en():
    s = i18n.t("language.lang_name_en", "en")
    assert "English" in s or s == "English"


def test_t_dotted_discovery_sort():
    assert i18n.t("discovery.sort_POPULARITY", "fr") == "Popularité"
    assert i18n.t("discovery.sort_POPULARITY", "en") == "Popularity"


def test_t_format_kwargs():
    s = i18n.t("language.success", "en", label="English")
    assert "English" in s


def test_guild_lang_none():
    assert i18n.guild_lang(None) == "fr"


def test_value_xp_titles():
    raw = i18n.value("xp.titles_global", "fr")
    assert isinstance(raw, list) and len(raw) > 0


def test_title_for_global_level_fr():
    t = i18n.title_for_global_level(0, "fr")
    assert "Novice" in t or "👶" in t
