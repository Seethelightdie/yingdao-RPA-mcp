from yingdao_rpa_mcp.win.params import build_launch_url, encode_param_value


def test_encode_special_chars_only():
    assert encode_param_value("a&b=c#d%e f") == "a%26b%3Dc%23d%25e%20f"


def test_chinese_kept_as_is():
    assert encode_param_value("张三") == "张三"  # 原仓库已验证影刀支持中文原样


def test_url_without_params():
    assert build_launch_url("abc-123") == "shadowbot:Run?robot-uuid=abc-123"


def test_url_with_params():
    url = build_launch_url("abc-123", {"name": "张三", "note": "a&b"})
    assert url == "shadowbot:Run?robot-uuid=abc-123&name=张三&note=a%26b"


def test_url_multi_params_ordered():
    url = build_launch_url("u", {"b": "2", "a": "1"})
    assert url == "shadowbot:Run?robot-uuid=u&b=2&a=1"  # 按调用方传入顺序（dict 保序）
