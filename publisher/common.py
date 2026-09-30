import contextlib
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


class PublishError(Exception):
    pass


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublishError(f"无法读取 {Path(path).name}：{exc}") from exc


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def inside(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise PublishError(f"资料不存在或位于资料文件夹之外：{relative}")
    return path


def base_url(value, allow_local=False):
    if not isinstance(value, str):
        raise PublishError("请填写店铺网址")
    parts = urlsplit(value)
    local = parts.hostname in {"127.0.0.1", "localhost", "::1"}
    if parts.scheme != "https" and not (allow_local and local and parts.scheme == "http"):
        raise PublishError("店铺和图片网址必须使用 HTTPS")
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise PublishError("网址不能包含登录信息、查询参数或片段")
    return value.rstrip("/")


def secret(config, key):
    name = config.get(key)
    if not isinstance(name, str) or not name or not os.environ.get(name):
        raise PublishError(f"请设置 {key} 指定的环境变量；密钥不要填进商品资料")
    return os.environ[name]


@contextlib.contextmanager
def exclusive(path):
    """进程退出后由操作系统释放锁，不删除其他执行者的锁文件。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise PublishError("这家店铺已有一批商品正在执行，请在结果返回后重试") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
