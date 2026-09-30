import base64
import json
import time
import urllib.error
import urllib.request
from .common import PublishError, encode


class RemoteError(PublishError):
    def __init__(self, status, ambiguous=False):
        self.status, self.ambiguous = status, ambiguous
        super().__init__(f"平台请求失败（{status}）；请检查店铺权限、商品资料或平台状态")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Http:
    def __init__(self, headers=None, timeout=40, attempts=3, sleeper=time.sleep):
        self.headers = headers or {}
        self.timeout, self.attempts, self.sleeper = timeout, attempts, sleeper
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, url, data=None, headers=None):
        body = encode(data) if isinstance(data, (dict, list)) else data
        merged = {"Accept": "application/json", **self.headers, **(headers or {})}
        if isinstance(data, (dict, list)):
            merged["Content-Type"] = "application/json; charset=utf-8"
        for attempt in range(self.attempts if method == "GET" else 1):
            request = urllib.request.Request(url, body, merged, method=method)
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    raw = response.read(10_000_001)
                    if len(raw) > 10_000_000:
                        raise PublishError("平台返回内容过大，请缩小单次查询范围")
                    try:
                        return json.loads(raw)
                    except (UnicodeError, json.JSONDecodeError) as exc:
                        raise RemoteError("返回内容不是有效 JSON", method != "GET") from exc
            except urllib.error.HTTPError as exc:
                # 不输出平台原始正文，它可能包含密钥、地址和个人资料。
                exc.close()
                if method == "GET" and exc.code in {429, 500, 502, 503, 504} and attempt + 1 < self.attempts:
                    retry = exc.headers.get("Retry-After", "")
                    delay = min(float(retry), 30) if retry.replace(".", "", 1).isdigit() else 2 ** attempt
                    self.sleeper(delay)
                    continue
                raise RemoteError(exc.code, method != "GET" and exc.code >= 500) from exc
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                if method == "GET" and attempt + 1 < self.attempts:
                    self.sleeper(2 ** attempt)
                    continue
                raise RemoteError("连接中断或超时", method != "GET") from exc


def basic(user, password):
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
