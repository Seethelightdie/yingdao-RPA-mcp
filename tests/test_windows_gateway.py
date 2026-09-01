import json
import os
from pathlib import Path

from yingdao_rpa_mcp.gateway.windows import WindowsGateway
from yingdao_rpa_mcp.models import STATE_EXITED, STATE_RUNNING, STATE_UNKNOWN
from yingdao_rpa_mcp.win.logparse import today_log_path

FIXTURE = (Path(__file__).parent / "fixtures" / "yingdao_sample.log").read_text(encoding="utf-8")


def make_gateway(tmp_path, alive_pids=None, log_text=None):
    users = tmp_path / "users"
    logdir = tmp_path / "log"
    (users / "user1" / "apps").mkdir(parents=True, exist_ok=True)
    logdir.mkdir()
    calls = {"launch": [], "stop": 0}
    gw = WindowsGateway(
        users_dir=users,
        log_dir=logdir,
        launch_fn=lambda url: calls["launch"].append(url),
        stop_fn=lambda: calls.__setitem__("stop", calls["stop"] + 1),
        alive_fn=lambda pid: pid in (alive_pids or set()),
    )
    if log_text is not None:
        today_log_path(logdir).write_text(log_text, encoding="utf-8")
    return gw, calls


def make_apps(tmp_path):
    """构造真实目录结构：uuid 为目录名，4 个候选 json、_temp 跳过、mtime 取 xbot_robot。"""
    apps = tmp_path / "users" / "user1" / "apps"
    a = apps / "uuid-a"
    (a / "xbot_robot").mkdir(parents=True)
    (a / "xbot_robot" / "package.json").write_text(
        json.dumps({"name": "报表机器人", "version": "1.5.2", "description": "d"}),
        encoding="utf-8")
    b = apps / "uuid-b"
    b.mkdir(parents=True)
    (b / "xbot_robot").mkdir()  # mtime 取自 xbot_robot 子目录；无 package.json → 落到第 2 候选
    (b / "package.json").write_text(json.dumps({"name": "采集机器人"}), encoding="utf-8")
    c = apps / "uuid-c"
    c.mkdir(parents=True)
    (c / "config.json").write_text("{}", encoding="utf-8")  # 命中第 4 候选，无 name → 名字=uuid
    d = apps / "uuid-d"
    d.mkdir(parents=True)
    (d / "robot.json").write_text("{bad json", encoding="utf-8")  # 坏 JSON → 落到下一候选
    (d / "config.json").write_text(json.dumps({"name": "兜底机器人"}), encoding="utf-8")
    temp = apps / "uuid-temp_temp"
    temp.mkdir()
    return apps


async def test_scan_structure(tmp_path):
    apps = make_apps(tmp_path)
    os.utime(apps / "uuid-a" / "xbot_robot", (1000000, 1000000))
    os.utime(apps / "uuid-b" / "xbot_robot", (2000000, 2000000))
    gw, _ = make_gateway(tmp_path)
    robots = await gw.scan()
    by_uuid = {r.uuid: r for r in robots}
    assert "uuid-temp_temp" not in by_uuid  # _temp 跳过
    assert by_uuid["uuid-a"].name == "报表机器人"      # 第 1 候选 xbot_robot/package.json
    assert by_uuid["uuid-b"].name == "采集机器人"      # 第 2 候选 package.json
    assert by_uuid["uuid-c"].name == "uuid-c"          # 第 4 候选无 name 字段 → 名字=uuid
    assert [r.uuid for r in robots][0] == "uuid-b"     # mtime 降序（b 的 2000000 > a 的 1000000）


async def test_launch_builds_url_and_records(tmp_path):
    gw, calls = make_gateway(tmp_path)
    await gw.launch("uuid-a", {"name": "张三", "note": "a&b"})
    assert calls["launch"] == ["shadowbot:Run?robot-uuid=uuid-a&name=张三&note=a%26b"]


async def test_stop_calls_primitives(tmp_path):
    gw, calls = make_gateway(tmp_path)
    await gw.stop()
    assert calls["stop"] == 1


async def test_status_uses_log_and_liveness(tmp_path):
    gw, _ = make_gateway(tmp_path, alive_pids={29100}, log_text=FIXTURE)
    st = await gw.status()
    assert st["c6073f48-0629-4eaa-9414-69de74c28757"].state == STATE_EXITED
    assert st["8f5e2b9c-1d3a-4e6b-9c8d-2a4b6c8d0e2f"].state == STATE_RUNNING  # pid 29100 存活


async def test_status_dead_pid_means_exited(tmp_path):
    gw, _ = make_gateway(tmp_path, alive_pids=set(), log_text=FIXTURE)
    st = await gw.status()
    assert st["8f5e2b9c-1d3a-4e6b-9c8d-2a4b6c8d0e2f"].state == STATE_EXITED  # 进程已死


async def test_status_single_uuid(tmp_path):
    gw, _ = make_gateway(tmp_path, alive_pids={29100}, log_text=FIXTURE)
    st = await gw.status("c6073f48-0629-4eaa-9414-69de74c28757")
    assert set(st) == {"c6073f48-0629-4eaa-9414-69de74c28757"}
    assert st["c6073f48-0629-4eaa-9414-69de74c28757"].state == STATE_EXITED


async def test_tail_log_missing_file(tmp_path):
    gw, _ = make_gateway(tmp_path)
    assert await gw.tail_log(10) == []  # 当日无日志返回空列表（spec 契约）


async def test_tail_log_reads_today(tmp_path):
    gw, _ = make_gateway(tmp_path, log_text=FIXTURE)
    lines = await gw.tail_log(3)
    assert len(lines) == 3
    assert "engine running" in lines[-1]


async def test_status_unknown_uuid_without_log(tmp_path):
    gw, _ = make_gateway(tmp_path)
    st = await gw.status("nonexistent-uuid")
    assert set(st) == {"nonexistent-uuid"}
    assert st["nonexistent-uuid"].state == STATE_UNKNOWN  # 显式 uuid 无日志 → unknown（接缝契约）
    assert any("未出现" in e for e in st["nonexistent-uuid"].evidence)


async def test_status_no_log_summary_empty(tmp_path):
    gw, _ = make_gateway(tmp_path)
    assert await gw.status() == {}  # 汇总路径无日志仍返回空 dict（回归钉）


async def test_scan_skips_unreadable_apps_dir(tmp_path, monkeypatch):
    make_apps(tmp_path)
    gw, _ = make_gateway(tmp_path)
    real_iterdir = Path.iterdir

    def denied_iterdir(self):
        if self.name == "apps":  # 模拟他人用户目录无读取权限
            raise PermissionError(13, "denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", denied_iterdir)
    assert await gw.scan() == []  # 权限降级：跳过不可读目录继续，不抛错


async def test_scan_robot_json_third_candidate(tmp_path):
    apps = make_apps(tmp_path)
    e = apps / "uuid-e"
    e.mkdir()
    (e / "robot.json").write_text(json.dumps({"name": "第三候选机器人"}), encoding="utf-8")
    gw, _ = make_gateway(tmp_path)
    by_uuid = {r.uuid: r for r in await gw.scan()}
    assert by_uuid["uuid-e"].name == "第三候选机器人"


async def test_scan_bad_json_falls_to_next_candidate(tmp_path):
    apps = make_apps(tmp_path)
    bare = apps / "uuid-bare"
    bare.mkdir()  # 无任何 package 文件 → 兜底分支
    gw, _ = make_gateway(tmp_path)
    by_uuid = {r.uuid: r for r in await gw.scan()}
    assert by_uuid["uuid-d"].name == "兜底机器人"           # robot.json 坏 → 跳到 config.json
    assert by_uuid["uuid-bare"].version == "未知"  # 无可解析 package → 原仓库 fallback 口径
