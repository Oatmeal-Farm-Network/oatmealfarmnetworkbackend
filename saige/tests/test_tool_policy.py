"""Unit tests for tool write policy."""
from tool_policy import filter_read_only_tools, is_write_tool


class _T:
    def __init__(self, name):
        self.name = name


def test_write_detection():
    assert is_write_tool("update_business_profile_tool")
    assert is_write_tool("create_field_tool")
    assert is_write_tool("confirm_seller_order_tool")
    assert not is_write_tool("get_business_profile_tool")
    assert not is_write_tool("list_my_fields_tool")
    assert not is_write_tool("get_weather_tool")


def test_filter_read_only():
    tools = [_T("get_weather_tool"), _T("update_animal_tool"), _T("list_my_fields_tool")]
    kept = filter_read_only_tools(tools)
    assert [t.name for t in kept] == ["get_weather_tool", "list_my_fields_tool"]
