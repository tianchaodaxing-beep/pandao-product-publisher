import copy
import datetime
import hashlib
import hmac
import time
from decimal import Decimal
from urllib.parse import quote, urlsplit
from .common import PublishError, secret, digest
from .transport import Http, RemoteError


PATH = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"


def authorization(access, secret_key, method, path, query="", stamp=None):
    stamp = stamp or datetime.datetime.now(datetime.timezone.utc).strftime("%y%m%dT%H%M%SZ")
    signature = hmac.new(secret_key.encode(), (stamp + method + path + query).encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access}, signed-date={stamp}, signature={signature}"


class Coupang:
    def __init__(self, config, state, namespace, sleeper=time.sleep):
        self.config, self.state, self.namespace, self.sleeper = config, state, namespace, sleeper
        self.access, self.secret = secret(config, "access_key_env"), secret(config, "secret_key_env")
        self.gateway = "https://api-gateway.coupang.com"
        # 本机契约检查用固定回环地址；不允许将真实凭据发往其他网关。
        if config.get("allow_local_http") and config.get("test_gateway"):
            test = urlsplit(config["test_gateway"])
            if test.scheme != "http" or test.hostname != "127.0.0.1":
                raise PublishError("接口检查地址只能是本机回环地址")
            self.gateway = config["test_gateway"].rstrip("/")
        self.http = Http(sleeper=sleeper)

    def request(self, method, path, data=None):
        value = self.http.request(method, self.gateway + path, data,
                                  {"Authorization": authorization(self.access, self.secret, method, path)})
        if value.get("code") != "SUCCESS":
            raise RemoteError("Coupang 拒绝了商品资料", False)
        return value.get("data")

    def find(self, product):
        found = {}
        for variant in product["variants"] or [product]:
            rows = self.request("GET", PATH + "/external-vendor-sku-codes/" + quote(variant["sku"], safe=""))
            for row in rows or []:
                if row.get("vendorId") != self.config["vendor_id"]:
                    raise PublishError("Coupang 回读卖家身份不一致，已停止")
                found[row["sellerProductId"]] = row
        if len(found) > 1:
            raise PublishError("这些商品编码对应多个 Coupang 商品，请分别处理")
        return next(iter(found.values()), None)

    def payload(self, product, media):
        body = copy.deepcopy(product["coupang"])
        body.update({"vendorId": self.config["vendor_id"], "sellerProductName": product["title"], "requested": False})
        variants = product["variants"] or [product]
        for item, variant in zip(body["items"], variants):
            item.update({"itemName": " / ".join(variant.get("attributes", {}).values()) or product["title"],
                         "salePrice": int(Decimal(variant["price"])), "maximumBuyCount": variant["stock"]})
            main = media["variants"].get(variant["sku"])
            imgs = [main] + media["images"] if main else media["images"]
            seen = set()
            imgs = [x for x in imgs if not (x["url"] in seen or seen.add(x["url"]))]
            for img in imgs:
                parts = urlsplit(img["url"])
                if parts.scheme != "https" or parts.port not in {None, 443} or len(img["url"]) > 200:
                    raise PublishError("Coupang 图片需要 200 字以内、443 端口的公开 HTTPS 地址")
            item["images"] = [{"imageOrder": i, "imageType": "REPRESENTATION" if i == 0 else "DETAIL", "vendorPath": x["url"]} for i, x in enumerate(imgs)]
            item["contents"] = [{"contentsType": "TEXT", "contentDetails": [{"content": product["description"], "detailType": "TEXT"}]}]
        return body

    def verify(self, remote, body):
        if remote.get("vendorId") != self.config["vendor_id"] or remote.get("sellerProductName") != body["sellerProductName"]:
            raise PublishError("Coupang 商品身份或名称回读不一致")
        actual = {x.get("externalVendorSku"): x for x in remote.get("items", [])}
        if set(actual) != {x["externalVendorSku"] for x in body["items"]}:
            raise PublishError("Coupang 商品规格回读不一致")
        for item in body["items"]:
            got = actual[item["externalVendorSku"]]
            for key in ("attributes", "notices", "certifications", "contents"):
                if got.get(key) != item.get(key):
                    raise PublishError("Coupang 商品回读不一致：" + key)
            if got.get("vendorItemId"):
                inventory = self.request("GET", PATH.replace("seller-products", "vendor-items") + f"/{got['vendorItemId']}/inventories")
                if inventory.get("salePrice") != item["salePrice"] or inventory.get("amountInStock") != item["maximumBuyCount"]:
                    raise PublishError("Coupang 实际售价或库存回读不一致")
            elif got.get("salePrice") != item["salePrice"] or got.get("maximumBuyCount") != item["maximumBuyCount"]:
                raise PublishError("Coupang 草稿售价或库存回读不一致")
            if len(got.get("images", [])) != len(item["images"]):
                raise PublishError("Coupang 图片数量回读不一致")
            for expected, image in zip(item["images"], got.get("images", [])):
                if image.get("imageType") != expected["imageType"] or image.get("imageOrder") != expected["imageOrder"]:
                    raise PublishError("Coupang 图片顺序或类型回读不一致")
                if image.get("vendorPath") and image["vendorPath"] != expected["vendorPath"]:
                    raise PublishError("Coupang 图片地址回读不一致")

    def result(self, product_id, remote, created, product, mode):
        status = remote.get("statusName", "平台未返回状态")
        item_ids = [x["vendorItemId"] for x in remote.get("items", []) if x.get("vendorItemId")]
        public_id = next((x.get("productId") for x in remote.get("items", []) if x.get("productId")), None)
        return {"id": product_id, "url": f"https://www.coupang.com/vp/products/{public_id}" if public_id else "",
                "status": status, "created": created, "verified": True, "vendor_item_ids": item_ids,
                "variant_count": len(product["variants"]) or 1, "approval_requested": mode == "publish"}

    def publish(self, product, media, mode):
        key = self.namespace + ":product:" + product["sku"]
        record = self.state.get(key)
        found = self.find(product)
        body = self.payload(product, media)
        desired_hash = digest({"body": body, "mode": mode})
        created = False
        if record.get("remote_id"):
            remote = self.request("GET", PATH + "/" + str(record["remote_id"]))
            if remote.get("vendorId") != self.config["vendor_id"]:
                raise PublishError("Coupang 回读卖家身份不一致，已停止")
            if record.get("verified_hash") == desired_hash:
                try:
                    self.verify(remote, body)
                except RemoteError:
                    raise
                except PublishError:
                    pass
                else:
                    return self.result(record["remote_id"], remote, False, product, mode)
            if found and found["sellerProductId"] != record["remote_id"]:
                raise PublishError("Coupang 商品编码与上次商品编号对应关系改变，已停止")
            found = {"sellerProductId": record["remote_id"]}
        if found:
            product_id = found["sellerProductId"]
            remote = self.request("GET", PATH + "/" + str(product_id))
            actual_items = {i.get("externalVendorSku"): i for i in remote.get("items", [])}
            if set(actual_items) != {i["externalVendorSku"] for i in body["items"]}:
                raise PublishError("现有 Coupang 规格与资料不同，请核对；工具不会删除规格")
            body["sellerProductId"] = product_id
            for item in body["items"]:
                actual = actual_items[item["externalVendorSku"]]
                for field in ("sellerProductItemId", "vendorItemId"):
                    if actual.get(field) is not None:
                        item[field] = actual[field]
            self.state.set(key, {"phase": "created", "remote_id": product_id})
            self.request("PUT", PATH, body)
            for item in body["items"]:
                if item.get("vendorItemId"):
                    path = PATH.replace("seller-products", "vendor-items") + "/" + str(item["vendorItemId"])
                    self.request("PUT", path + "/prices/" + str(item["salePrice"]))
                    self.request("PUT", path + "/quantities/" + str(item["maximumBuyCount"]))
        else:
            if record.get("phase") in {"creating", "uncertain", "created"}:
                raise PublishError("上次 Coupang 创建结果无法核实，请按商品编码在店铺查找；工具已停止重复创建")
            self.state.set(key, {"phase": "creating"})
            try:
                product_id = self.request("POST", PATH, body)
                created = True
            except RemoteError as exc:
                if exc.ambiguous:
                    for delay in (1, 2, 4):
                        self.sleeper(delay)
                        found = self.find(product)
                        if found:
                            product_id = found["sellerProductId"]
                            break
                    else:
                        self.state.set(key, {"phase": "uncertain"})
                        raise
                else:
                    self.state.set(key, {"phase": "failed"})
                    raise
            if type(product_id) is not int or product_id <= 0:
                self.state.set(key, {"phase": "uncertain"})
                raise PublishError("Coupang 没有返回有效商品编号")
            self.state.set(key, {"phase": "created", "remote_id": product_id})
        remote = self.request("GET", PATH + "/" + str(product_id))
        self.verify(remote, body)
        if mode == "publish":
            self.request("PUT", PATH + "/" + str(product_id) + "/approvals")
            remote = self.request("GET", PATH + "/" + str(product_id))
            self.verify(remote, body)
        self.state.set(key, {"phase": "created", "remote_id": product_id, "verified_hash": desired_hash})
        return self.result(product_id, remote, created, product, mode)
