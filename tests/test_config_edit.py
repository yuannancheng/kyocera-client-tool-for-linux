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
            [
                1,
                2,
                3,
                10,
                11,
                12,
                14,
                15,
                17,
                18,
                19,
                20,
                24,
                25,
                26,
                27,
                28,
                29,
                30,
                31,
                32,
                49,
                50,
                51,
                52,
                84,
                85,
            ],
        )

    def test_units_follow_the_official_control_mapping(self):
        setting = EDITABLE_BY_ID[51]
        self.assertEqual(dict(setting.choices), {3: "毫米", 4: "英寸"})
        self.assertTrue(editable_value_allowed(setting, 3))
        self.assertFalse(editable_value_allowed(setting, 2))

    def test_scaled_values_keep_the_device_integer_visible(self):
        setting = EDITABLE_BY_ID[52]
        self.assertEqual(display_edit_value(setting, 60), "300 秒（设备值 60）")

    def test_media_weight_rows_only_accept_reviewed_values(self):
        setting = EDITABLE_BY_ID[25]
        self.assertEqual(setting.label, "自定义 1 纸张重量")
        self.assertEqual(
            dict(setting.choices),
            {11: "普通 1", 12: "普通 2", 13: "普通 3"},
        )
        self.assertTrue(editable_value_allowed(setting, 11))
        self.assertTrue(editable_value_allowed(setting, 13))
        self.assertFalse(editable_value_allowed(setting, 10))
        self.assertEqual(display_edit_value(setting, 14), "重 1")

    def test_paper_mismatch_switch_only_accepts_audited_values(self):
        setting = EDITABLE_BY_ID[10]
        self.assertTrue(editable_value_allowed(setting, 0))
        self.assertTrue(editable_value_allowed(setting, 1))
        self.assertFalse(editable_value_allowed(setting, 2))


if __name__ == "__main__":
    unittest.main()
