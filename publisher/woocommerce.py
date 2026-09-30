import time
from decimal import Decimal
from urllib.parse import urlencode
from .common import PublishError, base_url, secret
from .transport import Http, RemoteError, basic


class WooCommerce:
    def __init__(self, config, state, namespace, sleeper=time.sleep):
        self.url = base_url(config["url"], config.get("allow_local_http", False)) + "/wp-json/wc/v3/products"
        self.http = Http({"Authorization": basic(secret(config, "consumer_key_env"), secret(config, "consumer_secret_env"))}, sleeper=sleeper)
        self.state, self.namespace, self.sleeper = state, namespace, sleeper

    def find(self, sku):
        rows = self.http.request("GET", self.url + "?" + urlencode({"sku": sku, "per_page": 100}))
        matches = [r for r in rows if r.get("sku") == sku]
        if len(matches) > 1:
            raise PublishError("店铺存在重复商品编码：" + sku)
        return matches[0] if matches else None

    def create(self, sku, url, body, finder, key):
        record = self.state.get(key)
        remote = finder(sku)
        if remote:
            self.state.set(key, {"phase": "created", "remote_id": remote["id"]})
            return remote, False
        if record.get("phase") in {"creating", "uncertain", "created"}:
            raise PublishError(f"{sku} 上次创建结果无法核实，请到店铺查找该编码；工具已停止重复创建")
        self.state.set(key, {"phase": "creating"})
        try:
            remote = self.http.request("POST", url, body)
        except RemoteError as exc:
            if exc.ambiguous:
                for delay in (1, 2, 4):
                    self.sleeper(delay)
                    remote = finder(sku)
                    if remote:
                        break
                else:
                    self.state.set(key, {"phase": "uncertain"})
                    raise
            else:
                self.state.set(key, {"phase": "failed"})
                raise
        if not isinstance(remote.get("id"), int) or remote["id"] <= 0:
            self.state.set(key, {"phase": "uncertain"})
            raise PublishError("平台未返回有效商品编号，请核对店铺后续接")
        self.state.set(key, {"phase": "created", "remote_id": remote["id"]})
        return remote, True

    def variations(self, product_id):
        result = []
        for page in range(1, 102):
            rows = self.http.request("GET", f"{self.url}/{product_id}/variations?per_page=100&page={page}")
            result.extend(rows)
            if len(rows) < 100:
                return result
        raise PublishError("规格数量过多，工具已停止修改")

    def verify_fields(self, remote, expected):
        for key, value in expected.items():
            actual = remote.get(key)
            if key == "regular_price":
                if Decimal(str(actual)) != Decimal(value):
                    raise PublishError("商品售价回读不一致")
            elif key == "images":
                if [x["id"] for x in actual or []] != [x["id"] for x in value]:
                    raise PublishError("商品图片回读不一致")
            elif key == "categories":
                if {x["id"] for x in actual or []} != {x["id"] for x in value}:
                    raise PublishError("商品分类回读不一致")
            elif key == "attributes":
                if value and "options" in value[0]:
                    wanted = {x["name"].casefold(): set(x["options"]) for x in value}
                    got = {x["name"].casefold(): set(x.get("options", [])) for x in actual or []}
                else:
                    wanted = {x["name"].casefold(): x["option"] for x in value}
                    got = {x["name"].casefold(): x.get("option") for x in actual or []}
                if wanted != got:
                    raise PublishError("商品规格属性回读不一致")
            elif key == "image":
                if (actual or {}).get("id") != value["id"]:
                    raise PublishError("规格图片回读不一致")
            elif key == "description":
                if (actual or "").strip() != value.strip():
                    raise PublishError("商品描述回读不一致，请检查店铺的内容过滤设置")
            elif actual != value:
                raise PublishError(f"商品字段回读不一致：{key}")

    def publish(self, product, media, mode):
        sku = product["sku"]
        key = self.namespace + ":product:" + sku
        body = {"sku": sku, "name": product["title"], "description": product["description"],
                "type": "variable" if product["variants"] else "simple",
                "images": [{"id": x["id"]} for x in media["images"]]}
        if "categories" in product:
            body["categories"] = [{"id": x} for x in product["categories"]]
        if product["variants"]:
            attrs = {}
            for variant in product["variants"]:
                for axis, option in variant["attributes"].items():
                    attrs.setdefault(axis, [])
                    if option not in attrs[axis]:
                        attrs[axis].append(option)
            body["attributes"] = [{"name": axis, "visible": True, "variation": True, "options": values} for axis, values in attrs.items()]
        else:
            body.update({"regular_price": product["price"], "manage_stock": True, "stock_quantity": product["stock"]})
        remote, created = self.create(sku, self.url, {**body, "status": "draft"}, self.find, key)
        if remote.get("type") != body["type"]:
            raise PublishError("现有商品类型与资料不一致，请分别使用新的商品编码")
        product_id = remote["id"]
        self.http.request("PUT", self.url + "/" + str(product_id), body)
        self.verify_fields(self.http.request("GET", self.url + "/" + str(product_id)), body)
        if product["variants"]:
            current = self.variations(product_id)
            wanted = {v["sku"] for v in product["variants"]}
            if any(v.get("sku") not in wanted for v in current):
                raise PublishError("店铺中存在资料未包含的规格，请补全资料；工具不会删除现有规格")
            for variant in product["variants"]:
                variant_body = {"sku": variant["sku"], "regular_price": variant["price"], "manage_stock": True,
                                "stock_quantity": variant["stock"],
                                "attributes": [{"name": k, "option": v} for k, v in variant["attributes"].items()]}
                if variant.get("image"):
                    variant_body["image"] = {"id": media["variants"][variant["sku"]]["id"]}
                def find_variant(code):
                    matches = [x for x in self.variations(product_id) if x.get("sku") == code]
                    if len(matches) > 1:
                        raise PublishError("店铺中存在重复规格编码")
                    return matches[0] if matches else None
                entry, _ = self.create(variant["sku"], f"{self.url}/{product_id}/variations", variant_body,
                                       find_variant, self.namespace + ":variant:" + variant["sku"])
                self.http.request("PUT", f"{self.url}/{product_id}/variations/{entry['id']}", variant_body)
                verified = self.http.request("GET", f"{self.url}/{product_id}/variations/{entry['id']}")
                self.verify_fields(verified, variant_body)
        target_status = "draft" if mode == "draft" else "publish"
        self.http.request("PUT", self.url + "/" + str(product_id), {"status": target_status})
        final = self.http.request("GET", self.url + "/" + str(product_id))
        self.verify_fields(final, {**body, "status": target_status})
        self.state.set(key, {"phase": "created", "remote_id": product_id})
        return {"id": product_id, "url": final.get("permalink", ""), "status": "已保存草稿" if mode == "draft" else "已发布",
                "created": created, "verified": True, "variant_count": len(product["variants"]) or 1}
