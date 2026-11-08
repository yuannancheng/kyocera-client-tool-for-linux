"""Reviewed integer properties that may be changed from the device page.

The catalog only contains fields whose UI-to-OID mapping and reversible
integer writes have direct evidence in the official configuration utility or
in prior MA2000w write audits.  Unknown, credential, network, Wi-Fi, reset,
string, and read-only telemetry fields remain excluded.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config_media import MEDIA_TYPE_NAMES, paper_weight_name


@dataclass(frozen=True)
class EditableIntegerSetting:
    item_id: int
    label: str
    description: str
    scale: int = 1
    unit: str | None = None
    choices: tuple[tuple[int, str], ...] = ()


_MEDIA_WEIGHT_IDS = (
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
)
_MEDIA_WEIGHT_CHOICES = (
    (11, "普通 1"),
    (12, "普通 2"),
    (13, "普通 3"),
)
_MEDIA_WEIGHT_DESCRIPTION = (
    "MA2000w 已验证设备值 11、12、13 可写入并恢复；"
    "显示名称来自 Client Tool 1.4.11.2 的纸张重量表。"
)


EDITABLE_INTEGER_SETTINGS: tuple[EditableIntegerSetting, ...] = (
    EditableIntegerSetting(
        item_id=1,
        label="睡眠时间",
        description="设备进入睡眠前等待的分钟数。",
        unit="分钟",
    ),
    EditableIntegerSetting(
        item_id=2,
        label="自动错误清除",
        description="设备自动清除可恢复错误。",
        choices=((0, "关闭"), (1, "开启")),
    ),
    EditableIntegerSetting(
        item_id=3,
        label="自动错误清除超时",
        description="官方控件以 5 秒为单位保存。",
        scale=5,
        unit="秒",
    ),
    EditableIntegerSetting(
        item_id=10,
        label="忽略纸张尺寸不匹配",
        description=(
            "MA2000w 已验证设备值 0 与 1 可写入并恢复；"
            "界面文字含义仍待确认。"
        ),
        choices=((0, "设备值 0"), (1, "设备值 1")),
    ),
    *(
        EditableIntegerSetting(
            item_id=item_id,
            label=(
                f"{MEDIA_TYPE_NAMES[item_id - 10]} 纸张重量"
                if MEDIA_TYPE_NAMES[item_id - 10].startswith("自定义")
                else f"{MEDIA_TYPE_NAMES[item_id - 10]}重量"
            ),
            description=_MEDIA_WEIGHT_DESCRIPTION,
            choices=_MEDIA_WEIGHT_CHOICES,
        )
        for item_id in _MEDIA_WEIGHT_IDS
    ),
    EditableIntegerSetting(
        item_id=49,
        label="打印浓度",
        description="值范围为 1–5。",
        choices=((1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5")),
    ),
    EditableIntegerSetting(
        item_id=50,
        label="静音模式",
        description="降低打印过程噪声。",
        choices=((0, "关闭"), (1, "开启")),
    ),
    EditableIntegerSetting(
        item_id=51,
        label="长度单位",
        description="设备显示长度时使用的单位。",
        choices=((3, "毫米"), (4, "英寸")),
    ),
    EditableIntegerSetting(
        item_id=52,
        label="送纸超时",
        description="官方控件以 5 秒为单位保存。",
        scale=5,
        unit="秒",
    ),
    EditableIntegerSetting(
        item_id=84,
        label="自动清除面板",
        description="设备自动清除面板输入或提示。",
        choices=((0, "关闭"), (1, "开启")),
    ),
    EditableIntegerSetting(
        item_id=85,
        label="面板自动清除时间",
        description="官方控件以 5 秒为单位保存。",
        scale=5,
        unit="秒",
    ),
)

EDITABLE_BY_ID = {
    setting.item_id: setting for setting in EDITABLE_INTEGER_SETTINGS
}


def editable_value_allowed(setting: EditableIntegerSetting, value: int) -> bool:
    """Return whether a value is in the reviewed explicit value set."""

    if setting.choices:
        return value in {choice for choice, _label in setting.choices}
    return value >= 0


def display_edit_value(setting: EditableIntegerSetting, value: int) -> str:
    """Render a reviewed device value without hiding the stored integer."""

    choices = dict(setting.choices)
    if value in choices:
        rendered = choices[value]
    elif weight_name := paper_weight_name(value):
        rendered = weight_name
    elif setting.scale != 1:
        rendered = f"{value * setting.scale} {setting.unit or ''}".strip()
    else:
        rendered = f"{value}{(' ' + setting.unit) if setting.unit else ''}"
    if setting.scale != 1:
        return f"{rendered}（设备值 {value}）"
    return rendered


__all__ = [
    "EDITABLE_BY_ID",
    "EDITABLE_INTEGER_SETTINGS",
    "EditableIntegerSetting",
    "display_edit_value",
    "editable_value_allowed",
]
