import unittest

from kyocera_monitor.config_edit import (
    EDITABLE_BY_ID,
    EDITABLE_INTEGER_SETTINGS,
    display_edit_value,
    editable_value_allowed,
)


class ConfigEditCatalogTests(unittest.TestCase):
    def test_catalog_is_the_reviewed_integer_subset(self):
        self.assertEqual(
            [setting.item_id for setting in EDITABLE_INTEGER_SETTINGS],
            [1, 2, 3, 49, 50, 51, 52, 84, 85],
        )

    def test_units_follow_the_official_control_mapping(self):
        setting = EDITABLE_BY_ID[51]
        self.assertEqual(dict(setting.choices), {3: "毫米", 4: "英寸"})
        self.assertTrue(editable_value_allowed(setting, 3))
        self.assertFalse(editable_value_allowed(setting, 2))

    def test_scaled_values_keep_the_device_integer_visible(self):
        setting = EDITABLE_BY_ID[52]
        self.assertEqual(display_edit_value(setting, 60), "300 秒（设备值 60）")


if __name__ == "__main__":
    unittest.main()
