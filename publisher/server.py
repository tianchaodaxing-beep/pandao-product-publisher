import json
import secrets
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .common import PublishError, inside, read_json
from .engine import run_plan
from .plan import build_plan


def create_server(port, runtime):
    runtime = Path(runtime).resolve()
    token = secrets.token_urlsafe(32)
    jobs, plans = {}, {}
    guard = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def reply(self, value, status=200, mime="application/json; charset=utf-8"):
            data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def authorized(self):
            return self.valid_host() and secrets.compare_digest(self.headers.get("X-Pandao-Token", ""), token)

        def do_GET(self):
            if not self.valid_host():
                return self.reply({"error": "请从本机入口打开"}, 403)
            if self.path == "/":
                html = Path(__file__).with_name("web.html").read_text(encoding="utf-8").replace("__TOKEN__", token)
                return self.reply(html.encode(), mime="text/html; charset=utf-8")
            if not self.authorized():
                return self.reply({"error": "请重新打开本机页面"}, 403)
            if self.path.startswith("/api/job/"):
                with guard:
                    job = jobs.get(self.path.rsplit("/", 1)[-1])
                return self.reply(job or {"error": "这批执行记录不存在"}, 200 if job else 404)
            return self.reply({"error": "页面不存在"}, 404)

        def do_POST(self):
            if not self.authorized() or self.headers.get("Origin", f"http://127.0.0.1:{self.server.server_port}") != f"http://127.0.0.1:{self.server.server_port}":
                return self.reply({"error": "请从本机页面发起"}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 20000:
                    raise PublishError("提交内容为空或过长")
                body = json.loads(self.rfile.read(length))
                if self.path == "/api/plan":
                    identifier = uuid.uuid4().hex
                    folder = runtime / "batches" / identifier
                    plan = build_plan(body["source"], body["shop"], folder, body.get("mode", "draft"))
                    with guard:
                        plans[identifier] = folder
                    return self.reply({"id": identifier, "folder": str(folder), "shop": plan["shop"]["name"], "mode": plan["mode"],
                                       "products": [{"sku": p["sku"], "title": p["title"], "variants": p["variants"],
                                                     "price": p.get("price"), "stock": p.get("stock"), "image_count": len(p["images"])} for p in plan["products"]]})
                if self.path == "/api/run":
                    identifier = body["id"]
                    with guard:
                        folder = plans.get(identifier)
                        if folder is None:
                            raise PublishError("请先生成发布清单")
                        if jobs.get(identifier, {}).get("status") == "running":
                            raise PublishError("这批商品正在执行，请等待结果")
                        jobs[identifier] = {"status": "running"}
                    def work():
                        try:
                            report = run_plan(folder, runtime)
                            value = {"status": "done", "report": report, "folder": str(folder)}
                        except PublishError as exc:
                            value = {"status": "failed", "error": str(exc)}
                        except Exception as exc:
                            import traceback
                            runtime.mkdir(parents=True, exist_ok=True)
                            with (runtime / "页面错误.log").open("a", encoding="utf-8") as handle:
                                traceback.print_exc(file=handle)
                            value = {"status": "failed", "error": f"执行失败（{type(exc).__name__}），请查看本机页面错误.log"}
                        with guard:
                            jobs[identifier] = value
                    threading.Thread(target=work, daemon=False).start()
                    return self.reply({"status": "running"}, 202)
                return self.reply({"error": "操作不存在"}, 404)
            except (PublishError, KeyError, TypeError, ValueError) as exc:
                return self.reply({"error": str(exc)}, 400)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port, runtime, open_browser=True):
    server = create_server(port, runtime)
    url = f"http://127.0.0.1:{server.server_port}/"
    print("商品发布页面：" + url, flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
