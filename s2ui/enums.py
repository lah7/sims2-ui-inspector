"""
Static constants for reference throughout the application.
"""
from enum import IntEnum


class UIScriptColumnText(IntEnum):
    """Text column IDs for the UI script tree"""
    GROUP_ID = 0
    INSTANCE_ID = 1
    CAPTION = 2
    GAME = 3
    PACKAGE = 4


class UIScriptColumnData(IntEnum):
    """Data column IDs for the UI script tree (user role)"""
    DBPF_ENTRY = 0
    UISCRIPT_ROOT = 1
    CHECKSUM = 3


class ElementsColumnText(IntEnum):
    """Text column IDs for the elements tree"""
    ELEMENT = 0
    SHOWN = 1
    IGNORE = 2
    CAPTION = 3
    ID = 4


class ElementsColumnData(IntEnum):
    """Data column IDs for the elements tree (user role)"""
    UISCRIPT_ELEMENT = 0
    ELEMENT_ID_S2UI = 2


class PropertiesColumnText(IntEnum):
    """Text column IDs for the properties tree"""
    ATTRIBUTE = 0
    VALUE = 1
