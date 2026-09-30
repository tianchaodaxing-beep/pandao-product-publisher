"""仅用于自动检查的本机接口样例；不代表生产平台验收。"""
import copy
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
from publisher.coupang import PATH, authorization


class Store:
    def __init__(self):
        self.media, self.products, self.variants, self.coupang, self.inventory = {}, {}, {}, {}, {}
        self.creates, self.uploads, self.approvals, self.updates = 0, 0, 0, 0
        self.fail_after_create, self.fail_before_create = False, False
        self.fail_sku, self.bad_readback, self.transient_reads = None, False, 0
        self.signed_requests = 0
        self.price_updates, self.stock_updates = 0, 0


@contextmanager
def shop_server():
    store = Store()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, obj, status=200):
            data = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.handle_request("GET")

        def do_POST(self):
            self.handle_request("POST")

        def do_PUT(self):
            self.handle_request("PUT")

        def handle_request(self, method):
            url = urlsplit(self.path)
            path, query = url.path, parse_qs(url.query)
            data = None
            if method in {"POST", "PUT"}:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if raw and "application/json" in self.headers.get("Content-Type", ""):
                    data = json.loads(raw)
            if method == "GET" and store.transient_reads:
                store.transient_reads -= 1
                return self.reply({}, 429)
            if path.startswith("/wp-json/wp/v2/media"):
                if not self.headers.get("Authorization", "").startswith("Basic "):
                    return self.reply({}, 401)
                if method == "POST":
                    store.uploads += 1
                    entry = {"id": len(store.media) + 1, "slug": query["slug"][0],
                             "source_url": "https://media.example.com/" + query["slug"][0] + ".jpg"}
                    store.media[entry["id"]] = entry
                    return self.reply(entry, 201)
                if path == "/wp-json/wp/v2/media":
                    return self.reply([m for m in store.media.values() if m["slug"] == query.get("slug", [""])[0]])
                return self.reply(store.media[int(path.rsplit("/", 1)[-1])])
            if path.startswith("/wp-json/wc/v3/products"):
                if not self.headers.get("Authorization", "").startswith("Basic "):
                    return self.reply({}, 401)
                segments = path.removeprefix("/wp-json/wc/v3/products").strip("/").split("/")
                if path == "/wp-json/wc/v3/products":
                    if method == "GET":
                        return self.reply([p for p in store.products.values() if p["sku"] == query.get("sku", [""])[0]])
                    if store.fail_before_create or data["sku"] == store.fail_sku:
                        return self.reply({}, 503 if store.fail_before_create else 400)
                    store.creates += 1
                    entry = {"id": len(store.products) + 100, "permalink": f"https://shop.example.com/products/{data['sku']}", **data}
                    store.products[entry["id"]] = entry
                    if store.fail_after_create:
                        store.fail_after_create = False
                        return self.reply({}, 503)
                    return self.reply(entry, 201)
                pid = int(segments[0])
                if len(segments) > 1 and segments[1] == "variations":
                    entries = store.variants.setdefault(pid, {})
                    if len(segments) == 2:
                        if method == "GET":
                            return self.reply(list(entries.values()))
                        store.creates += 1
                        entry = {"id": len(entries) + 1000, **data}
                        entries[entry["id"]] = entry
                        return self.reply(entry, 201)
                    vid = int(segments[2])
                    if method == "PUT":
                        store.updates += 1
                        entries[vid].update(data)
                    return self.reply(entries[vid])
                if method == "PUT":
                    store.updates += 1
                    store.products[pid].update(data)
                entry = copy.deepcopy(store.products[pid])
                if store.bad_readback:
                    entry["name"] = "平台错误名称"
                return self.reply(entry)
            if path.startswith(PATH) or "/marketplace/vendor-items/" in path:
                auth = self.headers.get("Authorization", "")
                try:
                    stamp = auth.split("signed-date=")[1].split(",")[0]
                except IndexError:
                    return self.reply({}, 401)
                if auth != authorization("test-access", "test-secret", method, path, stamp=stamp):
                    return self.reply({}, 401)
                store.signed_requests += 1
                if "/vendor-items/" in path:
                    segments = path.split("/vendor-items/")[1].split("/")
                    vid, action = int(segments[0]), segments[1]
                    if action == "prices":
                        store.price_updates += 1
                        store.inventory[vid]["salePrice"] = int(segments[2])
                    if action == "quantities":
                        store.stock_updates += 1
                        store.inventory[vid]["amountInStock"] = int(segments[2])
                    return self.reply({"code": "SUCCESS", "data": store.inventory[vid]})
                if "/external-vendor-sku-codes/" in path:
                    sku = unquote(path.rsplit("/", 1)[-1])
                    rows = [p for p in store.coupang.values() if any(i["externalVendorSku"] == sku for i in p["items"])]
                    return self.reply({"code": "SUCCESS", "data": rows})
                if method == "POST":
                    store.creates += 1
                    pid = len(store.coupang) + 9000
                    entry = {**data, "sellerProductId": pid, "statusName": "임시저장"}
                    for index, item in enumerate(entry["items"]):
                        item["sellerProductItemId"] = pid * 10 + index
                    store.coupang[pid] = entry
                    return self.reply({"code": "SUCCESS", "data": pid})
                if path == PATH:
                    store.updates += 1
                    store.coupang[data["sellerProductId"]].update(data)
                    return self.reply({"code": "SUCCESS", "data": data["sellerProductId"]})
                segments = path.removeprefix(PATH).strip("/").split("/")
                pid = int(segments[0])
                if len(segments) == 2 and segments[1] == "approvals":
                    store.approvals += 1
                    store.coupang[pid]["statusName"] = "승인대기중"
                return self.reply({"code": "SUCCESS", "data": store.coupang[pid]})
            return self.reply({}, 404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield store, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
