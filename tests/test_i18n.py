import re
import tempfile
import unittest
from pathlib import Path

from kyocera_monitor import updates, web
from kyocera_monitor.i18n import (
    ENGLISH_TRANSLATIONS,
    LANGUAGE_AUTO,
    LANGUAGE_EN,
    LANGUAGE_ZH,
    match_language,
    normalize_language_preference,
    render_localized_page,
    resolve_language,
)
from kyocera_monitor.preferences import SettingsError, SettingsStore


class LanguageResolutionTests(unittest.TestCase):
    def test_accept_language_prefers_highest_supported_quality(self):
        self.assertEqual(
            match_language("fr-FR,zh-CN;q=0.7,en-US;q=0.9"),
            LANGUAGE_EN,
        )
        self.assertEqual(
            match_language("en-GB;q=0.4,zh-Hans;q=0.8"),
            LANGUAGE_ZH,
        )

    def test_unsupported_or_disabled_languages_fall_back_to_chinese(self):
        self.assertEqual(match_language("fr-FR,de;q=0.8"), None)
        self.assertEqual(match_language("en-US;q=0"), None)
        self.assertEqual(
            resolve_language(LANGUAGE_AUTO, "fr-FR"),
            LANGUAGE_ZH,
        )

    def test_manual_language_wins_over_device_language(self):
        self.assertEqual(resolve_language("zh-CN", "en-US"), LANGUAGE_ZH)
        self.assertEqual(resolve_language("en-US", "zh-CN"), LANGUAGE_EN)

    def test_language_normalization_is_strict(self):
        self.assertEqual(normalize_language_preference(None), LANGUAGE_AUTO)
        self.assertEqual(normalize_language_preference("EN"), LANGUAGE_EN)
        self.assertEqual(normalize_language_preference("zh"), LANGUAGE_ZH)
        with self.assertRaises(ValueError):
            normalize_language_preference("fr-FR")


class TranslationCoverageTests(unittest.TestCase):
    def test_all_static_and_literal_translation_keys_exist(self):
        keys = set()
        for page in (web.OVERVIEW_HTML, web.DEVICE_HTML):
            keys.update(
                re.findall(
                    r'data-i18n(?:-placeholder|-aria-label)?="([^"]+)"',
                    page,
                )
            )
            keys.update(re.findall(r'\btr\("([^"]*)"', page))
        keys.update(
            re.findall(r'\bt\("([^"]*)"', updates.UPDATE_RUNTIME_SCRIPT)
        )
        self.assertEqual(keys - set(ENGLISH_TRANSLATIONS), set())

    def test_english_bootstrap_preserves_locale_and_translations(self):
        rendered = render_localized_page(
            web.OVERVIEW_HTML,
            preference=LANGUAGE_AUTO,
            effective=LANGUAGE_EN,
        )
        self.assertIn('<html lang="en-US">', rendered)
        self.assertIn('"locale":"en-US"', rendered)
        self.assertIn('"preference":"auto"', rendered)
        self.assertIn('"KYOCERA 打印机":"KYOCERA Printer"', rendered)


class LanguageSettingsTests(unittest.TestCase):
    def test_default_and_manual_language_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SettingsStore(Path(tmp) / "settings.json")
            self.assertEqual(store.load()["language"], LANGUAGE_AUTO)
            saved = store.update_language(LANGUAGE_EN)
            self.assertEqual(saved["language"], LANGUAGE_EN)
            self.assertEqual(store.load()["language"], LANGUAGE_EN)

    def test_invalid_language_does_not_change_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SettingsStore(Path(tmp) / "settings.json")
            store.update_language(LANGUAGE_ZH)
            with self.assertRaises(SettingsError):
                store.update_language("fr-FR")
            self.assertEqual(store.load()["language"], LANGUAGE_ZH)


if __name__ == "__main__":
    unittest.main()
