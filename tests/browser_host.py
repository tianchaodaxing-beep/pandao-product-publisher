"""浏览器检查的本机样例环境，退出后清理临时资料。"""
import json
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from contract_server import shop_server
from publisher.common import write_json
from publisher.server import create_server

os.environ.update({"WOO_KEY": "test-key", "WOO_SECRET": "test-secret", "WP_USER": "test-user", "WP_PASSWORD": "test-password"})
with tempfile.TemporaryDirectory() as temp, shop_server() as (store, url):
    root = Path(temp)
    source = root / "商品资料"
    source.mkdir()
    Image.new("RGB", (800, 1000), (57, 100, 148)).save(source / "main.jpg")
    write_json(source / "product.json", {"sku": "BROWSER-DEMO-001", "title": "浏览器检查用演示商品", "description": "仅用于本机自动检查",
                                         "images": ["main.jpg"], "price": "29.90", "stock": 3})
    shop = root / "shop.json"
    write_json(shop, {"name": "本机接口样例店铺", "platform": "woocommerce", "url": url, "allow_local_http": True,
                      "consumer_key_env": "WOO_KEY", "consumer_secret_env": "WOO_SECRET",
                      "media": {"type": "wordpress", "url": url, "username_env": "WP_USER", "password_env": "WP_PASSWORD"}})
    server = create_server(0, root / "runtime")
    print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}", "source": str(source), "shop": str(shop)}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
