import copy
import hashlib
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from publisher.common import PublishError, digest, exclusive, write_json
from publisher.coupang import authorization
from publisher.engine import run_plan
from publisher.plan import build_plan, load_plan
from publisher.server import create_server
from publisher.transport import Http, RemoteError
from contract_server import shop_server


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "资料"
        self.source.mkdir()
        self.item = {"sku": "中文/SKU 01", "title": "真实流程样例商品", "description": "<p>自动检查用资料</p>",
                     "images": ["main.png"], "price": "19.90", "stock": 8}
        Image.new("RGBA", (700, 1200), (90, 140, 220, 180)).save(self.source / "main.png")
        self.env = patch.dict(os.environ, {"WOO_KEY": "test-key", "WOO_SECRET": "test-secret", "WP_USER": "test-user",
                                          "WP_PASSWORD": "test-password", "CP_ACCESS": "test-access", "CP_SECRET": "test-secret"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def config(self, url, platform="woocommerce"):
        result = {"platform": platform, "name": "本机接口样例店铺", "allow_local_http": True,
                  "media": {"type": "wordpress", "url": url, "username_env": "WP_USER", "password_env": "WP_PASSWORD"}}
        if platform == "woocommerce":
            result.update({"url": url, "consumer_key_env": "WOO_KEY", "consumer_secret_env": "WOO_SECRET"})
        else:
            result.update({"vendor_id": "TEST-VENDOR", "access_key_env": "CP_ACCESS", "secret_key_env": "CP_SECRET", "test_gateway": url})
        return result

    def plan(self, url, mode="draft", platform="woocommerce", folder="清单", item=None):
        write_json(self.source / "product.json", item or self.item)
        write_json(self.root / "shop.json", self.config(url, platform))
        build_plan(self.source, self.root / "shop.json", self.root / folder, mode)
        return self.root / folder

    def execute(self, folder):
        return run_plan(folder, self.root / "runtime", sleeper=lambda delay: None)

    def cp_item(self):
        item = copy.deepcopy(self.item)
        item["price"] = "19000"
        item["coupang"] = {"displayCategoryCode": 999999, "saleStartedAt": "2026-09-30T00:00:00", "saleEndedAt": "2099-01-01T00:00:00",
                           "vendorUserId": "test-user", "deliveryMethod": "SEQUENTIAL", "deliveryCompanyCode": "CJGLS",
                           "deliveryChargeType": "FREE", "deliveryCharge": 0, "freeShipOverAmount": 0,
                           "deliveryChargeOnReturn": 3000, "remoteAreaDeliverable": "N", "unionDeliveryType": "NOT_UNION_DELIVERY",
                           "returnCenterCode": "TEST-RETURN", "returnChargeName": "自动检查样例", "companyContactNumber": "000-0000-0000",
                           "returnZipCode": "00000", "returnAddress": "自动检查用虚构地址", "returnAddressDetail": "样例",
                           "returnCharge": 3000, "outboundShippingPlaceCode": "TEST-OUTBOUND", "items": [
                               {"externalVendorSku": item["sku"], "originalPrice": 19000, "maximumBuyForPerson": 0,
                                "maximumBuyForPersonPeriod": 1, "outboundShippingTimeDay": 2, "unitCount": 1,
                                "adultOnly": "EVERYONE", "taxType": "TAX", "parallelImported": "NOT_PARALLEL_IMPORTED",
                                "overseasPurchased": "NOT_OVERSEAS_PURCHASED", "pccNeeded": False,
                                "attributes": [], "notices": [], "certifications": [], "searchTags": []}]}
        return item

    def test_woo_create_publish_readback_and_no_duplicate(self):
        with shop_server() as (store, url):
            folder = self.plan(url, "publish")
            report = self.execute(folder)
            self.assertTrue(report["complete"], report)
            self.assertEqual((store.creates, store.uploads), (1, 1))
            self.assertEqual(report["results"][0]["status"], "已发布")
            self.assertTrue(self.execute(folder)["complete"])
            self.assertEqual((store.creates, store.uploads), (1, 1))
            self.assertEqual(json.loads((folder / "result.json").read_text(encoding="utf-8"))["passed"], 1)

    def test_variants_created_verified_and_resumed(self):
        self.item.pop("price")
        self.item.pop("stock")
        self.item["variants"] = [{"sku": "V-白", "price": "19.90", "stock": 3, "attributes": {"颜色": "白"}, "image": "main.png"},
                                 {"sku": "V-蓝", "price": "21.00", "stock": 4, "attributes": {"颜色": "蓝"}}]
        with shop_server() as (store, url):
            folder = self.plan(url, "publish")
            self.assertTrue(self.execute(folder)["complete"])
            self.assertEqual(store.creates, 3)
            self.assertTrue(self.execute(folder)["complete"])
            self.assertEqual(store.creates, 3)

    def test_existing_product_updated_without_recreation(self):
        with shop_server() as (store, url):
            folder = self.plan(url)
            self.assertTrue(self.execute(folder)["complete"])
            self.item["title"], self.item["stock"] = "修改后的商品名称", 11
            folder2 = self.plan(url, folder="第二批")
            self.assertTrue(self.execute(folder2)["complete"])
            self.assertEqual(store.creates, 1)
            self.assertEqual(next(iter(store.products.values()))["stock_quantity"], 11)

    def test_create_503_after_success_recovers_by_sku(self):
        with shop_server() as (store, url):
            store.fail_after_create = True
            report = self.execute(self.plan(url))
            self.assertTrue(report["complete"], report)
            self.assertEqual(store.creates, 1)

    def test_uncertain_create_is_not_blindly_retried(self):
        with shop_server() as (store, url):
            store.fail_before_create = True
            folder = self.plan(url)
            self.assertFalse(self.execute(folder)["complete"])
            store.fail_before_create = False
            report = self.execute(folder)
            self.assertFalse(report["complete"])
            self.assertEqual(store.creates, 0)
            self.assertIn("停止重复创建", report["results"][0]["error"])

    def test_bad_platform_readback_does_not_publish(self):
        with shop_server() as (store, url):
            store.bad_readback = True
            report = self.execute(self.plan(url, "publish"))
            self.assertFalse(report["complete"])
            self.assertEqual(next(iter(store.products.values()))["status"], "draft")

    def test_independent_products_continue_after_one_failure(self):
        (self.source / "product.json").unlink(missing_ok=True)
        for sku in ("BAD", "GOOD"):
            directory = self.source / sku
            directory.mkdir()
            Image.new("RGB", (1000, 1000), "blue").save(directory / "main.png")
            write_json(directory / "product.json", {**self.item, "sku": sku})
        with shop_server() as (store, url):
            store.fail_sku = "BAD"
            write_json(self.root / "shop.json", self.config(url))
            folder = self.root / "清单"
            build_plan(self.source, self.root / "shop.json", folder)
            report = self.execute(folder)
            self.assertEqual((report["processed"], report["passed"], report["failed"]), (2, 1, 1))

    def test_image_processing_preserves_original_and_removes_metadata(self):
        before = hashlib.sha256((self.source / "main.png").read_bytes()).hexdigest()
        folder = self.plan("http://127.0.0.1:8888")
        plan = load_plan(folder)
        asset = plan["products"][0]["images"][0]
        with Image.open(folder / asset["file"]) as image:
            self.assertEqual(image.size, (1000, 1000))
            self.assertFalse(image.getexif())
        self.assertEqual(before, hashlib.sha256((self.source / "main.png").read_bytes()).hexdigest())

    def test_tampered_plan_and_image_are_rejected(self):
        folder = self.plan("http://127.0.0.1:8888")
        plan = load_plan(folder)
        asset = folder / plan["products"][0]["images"][0]["file"]
        asset.write_bytes(b"changed")
        with self.assertRaises(PublishError):
            load_plan(folder)
        plan["mode"] = "publish"
        write_json(folder / "plan.json", plan)
        with self.assertRaises(PublishError):
            load_plan(folder)

    def test_source_path_escape_and_duplicate_sku_rejected(self):
        self.item["images"] = ["../secret.png"]
        with self.assertRaises(PublishError):
            self.plan("http://127.0.0.1:8888")
        self.item["images"] = ["main.png"]
        self.item["variants"] = [{"sku": self.item["sku"], "price": "1", "stock": 1, "attributes": {"颜色": "蓝"}}]
        with self.assertRaises(PublishError):
            self.plan("http://127.0.0.1:8888", folder="第二批")

    def test_chinese_csv_input(self):
        (self.source / "products.csv").write_text("商品编码,商品名称,商品描述,售价,库存,分类编号,图片\nCSV-01,表格商品,样例,20,3,,main.png\n", encoding="utf-8-sig")
        folder = self.plan("http://127.0.0.1:8888")
        self.assertEqual(load_plan(folder)["products"][0]["sku"], "CSV-01")

    def test_missing_credentials_have_no_remote_mutation(self):
        with shop_server() as (store, url):
            folder = self.plan(url)
            with patch.dict(os.environ, {"WOO_KEY": ""}):
                with self.assertRaises(PublishError):
                    self.execute(folder)
            self.assertEqual((store.creates, store.uploads), (0, 0))

    def test_coupang_create_draft_signed_and_readback(self):
        with shop_server() as (store, url):
            folder = self.plan(url, platform="coupang", item=self.cp_item())
            report = self.execute(folder)
            self.assertTrue(report["complete"], report)
            self.assertEqual((store.creates, store.approvals), (1, 0))
            self.assertEqual(report["results"][0]["status"], "임시저장")
            self.assertEqual(report["results"][0]["url"], "")
            self.assertGreater(store.signed_requests, 2)

    def test_coupang_approval_is_not_claimed_as_published_and_rerun_skips(self):
        with shop_server() as (store, url):
            folder = self.plan(url, "publish", "coupang", item=self.cp_item())
            report = self.execute(folder)
            self.assertTrue(report["complete"], report)
            self.assertEqual(report["results"][0]["status"], "승인대기중")
            self.assertTrue(self.execute(folder)["complete"])
            self.assertEqual((store.creates, store.approvals, store.updates), (1, 1, 0))

    def test_coupang_approved_price_and_inventory_use_dedicated_endpoints(self):
        with shop_server() as (store, url):
            item = self.cp_item()
            folder = self.plan(url, platform="coupang", item=item)
            self.assertTrue(self.execute(folder)["complete"])
            entry = next(iter(store.coupang.values()))
            entry["statusName"] = "승인완료"
            entry["items"][0]["vendorItemId"] = 600001
            store.inventory[600001] = {"salePrice": 19000, "amountInStock": 8, "onSale": True}
            item["price"], item["stock"] = "20000", 12
            folder2 = self.plan(url, platform="coupang", folder="第二批", item=item)
            report = self.execute(folder2)
            self.assertTrue(report["complete"], report)
            self.assertEqual((store.price_updates, store.stock_updates), (1, 1))
            self.assertEqual(store.inventory[600001]["amountInStock"], 12)

    def test_coupang_missing_logistics_rejected_before_network(self):
        with self.assertRaises(PublishError):
            self.plan("http://127.0.0.1:8888", platform="coupang")

    def test_get_rate_limit_has_bounded_retry(self):
        with shop_server() as (store, url):
            store.transient_reads = 2
            http = Http({"Authorization": "Basic dGVzdA=="}, sleeper=lambda _: None)
            self.assertEqual(http.request("GET", url + "/wp-json/wp/v2/media?slug=x"), [])
            store.transient_reads = 4
            with self.assertRaises(RemoteError):
                http.request("GET", url + "/wp-json/wp/v2/media?slug=x")
            self.assertEqual(store.transient_reads, 1)

    def test_runtime_lock_prevents_parallel_execution(self):
        lock = self.root / "lock"
        with exclusive(lock):
            with self.assertRaises(PublishError):
                with exclusive(lock):
                    pass

    def test_coupang_hmac_fixed_vector(self):
        value = authorization("access", "secret", "GET", "/a", "x=1", "260930T010203Z")
        import hmac
        expected = hmac.new(b"secret", b"260930T010203ZGET/ax=1", hashlib.sha256).hexdigest()
        self.assertTrue(value.endswith("signature=" + expected))

    def test_local_ui_requires_token_and_correct_host(self):
        server = create_server(0, self.root / "runtime")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            html = urllib.request.urlopen(url).read().decode()
            self.assertIn("把商品资料交给店铺", html)
            with self.assertRaises(urllib.error.HTTPError) as blocked:
                urllib.request.urlopen(urllib.request.Request(url + "/api/plan", b"{}", method="POST"))
            self.assertEqual(blocked.exception.code, 403)
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(urllib.request.Request(url, headers={"Host": "evil.example.com"}))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
