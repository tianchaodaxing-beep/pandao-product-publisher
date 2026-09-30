import csv
import datetime
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from .common import PublishError, base_url, digest, inside, read_json, write_json


def price(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number.as_tuple().exponent < -2:
            raise ValueError()
        return format(number, "f")
    except (ValueError, InvalidOperation) as exc:
        raise PublishError("售价应为非负数字，最多两位小数") from exc


def quantity(value):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise PublishError("库存应为非负整数") from exc
    if isinstance(value, bool) or str(value) != str(number) or number < 0:
        raise PublishError("库存应为非负整数")
    return number


def load_products(folder):
    folder = Path(folder).resolve()
    csv_path = folder / "products.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows or len(rows) > 500:
            raise PublishError("商品表格需包含 1 至 500 个商品")
        try:
            for row in rows:
                [int(s.strip()) for s in row.get("分类编号", "").split(";") if s.strip()]
        except ValueError as exc:
            raise PublishError("表格分类编号应为正整数") from exc
        return [(folder, {"sku": r.get("商品编码"), "title": r.get("商品名称"),
                         "description": r.get("商品描述", ""), "price": r.get("售价"),
                         "stock": r.get("库存"), "images": [s.strip() for s in r.get("图片", "").split(";") if s.strip()],
                         "categories": [int(s.strip()) for s in r.get("分类编号", "").split(";") if s.strip()]}) for r in rows]
    paths = sorted(folder.rglob("product.json"))
    if not paths:
        raise PublishError("资料文件夹中没有 product.json 或 products.csv")
    if len(paths) > 500:
        raise PublishError("单批最多 500 个商品，请分批处理")
    if any(not p.resolve().is_relative_to(folder) for p in paths):
        raise PublishError("商品资料不能引用资料文件夹之外的文件")
    return [(p.parent, read_json(p)) for p in paths]


def validate_product(value):
    if not isinstance(value, dict):
        raise PublishError("商品资料应为对象")
    result = dict(value)
    for key, title in [("sku", "商品编码"), ("title", "商品名称")]:
        if not isinstance(result.get(key), str) or not result[key].strip() or len(result[key]) > 200:
            raise PublishError(f"请填写有效的{title}（最多 200 字）")
        result[key] = result[key].strip()
    result["description"] = str(result.get("description", ""))
    images = result.get("images")
    if not isinstance(images, list) or not images or any(not isinstance(i, str) for i in images):
        raise PublishError(f"{result['sku']} 至少需要一张图片")
    variants = result.get("variants", [])
    if not isinstance(variants, list) or len(variants) > 100:
        raise PublishError("单个商品最多 100 个规格")
    if variants:
        axes = None
        combinations = set()
        for item in variants:
            if not isinstance(item.get("sku"), str) or not item["sku"].strip():
                raise PublishError("每个规格需要独立商品编码")
            item["price"], item["stock"] = price(item.get("price")), quantity(item.get("stock"))
            attrs = item.get("attributes")
            if not isinstance(attrs, dict) or not attrs or any(not k or not isinstance(v, str) or not v for k, v in attrs.items()):
                raise PublishError("每个规格需要属性名称和属性值")
            if axes is None:
                axes = set(attrs)
            if set(attrs) != axes:
                raise PublishError("同一商品的规格属性名称必须一致")
            combo = tuple(sorted(attrs.items()))
            if combo in combinations:
                raise PublishError("规格组合不能重复")
            combinations.add(combo)
    else:
        result["price"], result["stock"] = price(result.get("price")), quantity(result.get("stock"))
    result["variants"] = variants
    categories = result.get("categories", [])
    if not isinstance(categories, list) or any(type(x) is not int or x <= 0 for x in categories):
        raise PublishError("分类编号应为正整数")
    return result


def prepare_image(root, source, destination, main=False):
    src = inside(root, source)
    try:
        with Image.open(src) as image:
            if getattr(image, "n_frames", 1) > 1:
                raise PublishError("动画图片请先选定静态商品图，工具不会自动丢弃动画帧")
            image = ImageOps.exif_transpose(image)
            image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                rgba = image.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, "white")
                rgb.paste(rgba, mask=rgba.getchannel("A"))
                image = rgb
            else:
                image = image.convert("RGB")
            if main:
                image = ImageOps.pad(image, (1000, 1000), method=Image.Resampling.LANCZOS, color="white")
            import io
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=92, optimize=True)
            data = buffer.getvalue()
            width, height = image.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise PublishError(f"图片无法读取：{source}") from exc
    if len(data) >= 5_000_000:
        raise PublishError(f"图片处理后仍超过 5 MB：{source}")
    sha = hashlib.sha256(data).hexdigest()
    path = destination / (sha + ".jpg")
    path.write_bytes(data)
    return {"file": "assets/" + path.name, "sha256": sha, "width": width, "height": height}


def validate_shop(config):
    if config.get("platform") not in {"woocommerce", "coupang"}:
        raise PublishError("请选择已支持的 WooCommerce 或 Coupang")
    if not isinstance(config.get("name"), str) or not config["name"].strip():
        raise PublishError("请填写目标店铺名称")
    if config["platform"] == "woocommerce":
        base_url(config.get("url"), config.get("allow_local_http", False))
        for field in ("consumer_key_env", "consumer_secret_env"):
            if not config.get(field):
                raise PublishError(f"店铺配置缺少 {field}")
    else:
        for field in ("vendor_id", "access_key_env", "secret_key_env"):
            if not config.get(field):
                raise PublishError(f"店铺配置缺少 {field}")
    media = config.get("media", {})
    if media.get("type") != "wordpress":
        raise PublishError("首版需配置 WordPress 图片库，用于自动上传本机图片")
    base_url(media.get("url"), config.get("allow_local_http", False))
    for field in ("username_env", "password_env"):
        if not media.get(field):
            raise PublishError(f"图片库配置缺少 {field}")
    if config["platform"] == "woocommerce" and config["url"].rstrip("/") != media["url"].rstrip("/"):
        raise PublishError("WooCommerce 图片库必须是目标店铺自身的 WordPress 图片库")


def validate_coupang(product, config):
    template = product.get("coupang")
    if not isinstance(template, dict):
        raise PublishError(f"{product['sku']} 缺少 Coupang 类目、物流和资质资料（coupang 对象）")
    required = ["displayCategoryCode", "saleStartedAt", "saleEndedAt", "vendorUserId", "deliveryMethod",
                "deliveryCompanyCode", "deliveryChargeType", "deliveryCharge", "freeShipOverAmount", "deliveryChargeOnReturn",
                "remoteAreaDeliverable", "unionDeliveryType", "returnCenterCode",
                "returnChargeName", "companyContactNumber", "returnZipCode", "returnAddress",
                "returnAddressDetail", "returnCharge", "outboundShippingPlaceCode", "items"]
    missing = [key for key in required if key not in template or template[key] is None]
    if missing:
        raise PublishError(f"{product['sku']} 的 Coupang 资料缺少：" + "、".join(missing))
    if len(product["title"]) > 100 or len(product["images"]) > 10:
        raise PublishError("Coupang 商品名称最多 100 字，商品图片最多 10 张")
    items = template["items"]
    variants = product["variants"] or [product]
    if not isinstance(items, list) or len(items) != len(variants):
        raise PublishError("Coupang items 必须与商品规格逐项对应")
    for item, variant in zip(items, variants):
        if item.get("externalVendorSku") != variant["sku"]:
            raise PublishError("Coupang externalVendorSku 必须与对应商品编码一致")
        for key in ("originalPrice", "maximumBuyForPerson", "maximumBuyForPersonPeriod", "outboundShippingTimeDay",
                    "unitCount", "adultOnly", "taxType", "parallelImported", "overseasPurchased",
                    "pccNeeded", "attributes", "notices", "certifications", "searchTags"):
            if key not in item:
                raise PublishError(f"{variant['sku']} 的 Coupang 资料缺少 {key}")
        if Decimal(variant["price"]) != Decimal(variant["price"]).to_integral():
            raise PublishError("Coupang 韩元售价必须为整数")
        if variant["stock"] > 99999:
            raise PublishError("Coupang 库存最多 99999")
    if template.get("vendorId") not in {None, config["vendor_id"]}:
        raise PublishError("商品资料中的卖家编号与目标店铺不一致")


def build_plan(source, shop_file, output, mode="draft"):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_dir():
        raise PublishError("商品资料文件夹不存在")
    if mode not in {"draft", "publish"}:
        raise PublishError("发布方式必须为 draft 或 publish")
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise PublishError("发布清单和原始资料应分别存放在不同文件夹")
    if output.exists() and any(output.iterdir()):
        raise PublishError("清单文件夹已有内容，请使用一个新的空文件夹")
    config = read_json(shop_file)
    validate_shop(config)
    products = []
    seen = set()
    for root, item in load_products(source):
        item = validate_product(item)
        skus = [item["sku"]] + [v["sku"] for v in item["variants"]]
        if len(set(skus)) != len(skus) or any(s in seen for s in skus):
            raise PublishError("商品或规格编码重复：" + item["sku"])
        seen.update(skus)
        if item.get("description_file"):
            item["description"] = inside(root, item.pop("description_file")).read_text(encoding="utf-8-sig")
        if config["platform"] == "coupang":
            validate_coupang(item, config)
        products.append((root, item))
    assets = output / "assets"
    assets.mkdir(parents=True)
    normalized = []
    for root, item in products:
        item["images"] = [prepare_image(root, image, assets, main=index == 0) for index, image in enumerate(item["images"])]
        for variant in item["variants"]:
            if variant.get("image"):
                variant["image"] = prepare_image(root, variant["image"], assets, main=True)
        normalized.append(item)
    plan = {"version": 1, "created_at": datetime.datetime.now().astimezone().isoformat(),
            "shop": config, "mode": mode, "products": normalized}
    plan["digest"] = digest(plan)
    write_json(output / "plan.json", plan)
    rows = ["# 商品发布清单", "", f"目标店铺：{config['name']}", f"平台：{config['platform']}",
            "发布方式：" + ("保存草稿" if mode == "draft" else "发布商品（Coupang 为提交审核）"), "",
            "| 商品编码 | 名称 | 规格数 | 图片数 |", "| --- | --- | --- | --- |"]
    for item in normalized:
        rows.append(f"| {item['sku'].replace('|', '/')} | {item['title'].replace('|', '/')} | {len(item['variants']) or 1} | {len(item['images'])} |")
    rows += ["", "执行前请核对 plan.json 中的售价、库存、属性、物流和资质资料。"]
    (output / "发布清单.md").write_text("\n".join(rows), encoding="utf-8")
    return plan


def load_plan(folder):
    folder = Path(folder).resolve()
    plan = read_json(folder / "plan.json")
    stored = plan.get("digest")
    if digest({k: v for k, v in plan.items() if k != "digest"}) != stored:
        raise PublishError("发布清单已改变，请重新生成并核对")
    validate_shop(plan["shop"])
    for item in plan["products"]:
        images = item["images"] + [v["image"] for v in item["variants"] if v.get("image")]
        for img in images:
            if hashlib.sha256(inside(folder, img["file"]).read_bytes()).hexdigest() != img["sha256"]:
                raise PublishError("上传图片已改变，请重新生成清单")
    return plan
