# PANDAO product publisher

[简体中文](README.md) · English

Give the tool a batch of product data: it prepares images, uploads them to a media library, fills product details and variants, saves drafts or submits for publication, then reads back IDs and platform status.

Supports **Coupang Korea** and **WooCommerce**. For teams with existing product data and repeated listing or maintenance work. Execution does not use a language model.

Real API adapters are implemented. Automated checks use local API fixtures. The first production-store product acceptance test has not been completed: connect your store, save one real draft and check it before a batch.

[Source](https://github.com/tianchaodaxing-beep/pandao-product-publisher) · [Download](https://github.com/tianchaodaxing-beep/pandao-product-publisher/releases/latest)

## Capabilities

- Read multiple product folders or a product spreadsheet.
- Prepare the main and variant images on a white 1000 × 1000 canvas; retain proportions for other images. Original images are preserved.
- Upload to a WordPress media library and reuse existing images.
- Find products by SKU, create or maintain products, and support variants and variant images.
- Save WooCommerce drafts or publish; save Coupang drafts or submit for review.
- Read back names, variants, images, price, stock and status, then save conclusions.
- Continue other products after an individual failure and resume using the original SKUs.
- After a timed-out create request, check the platform first. If the outcome cannot be established, stop duplicate creation attempts.

Coupang controls review and sale visibility. Receiving an ID does not establish review approval. When the platform returns no public page ID, the tool does not invent a product URL.

## Install and open

Requires Python 3.11 or later:

```sh
python -m pip install -e .
python -m publisher --lang en serve
```

Windows also includes `Start-publisher.cmd`. The page is local. Click **English** to switch the interface or **中文** to return; current inputs are retained. Command-line help and status use `--lang zh` or `--lang en` before the subcommand.

## Store configuration

Copy `examples/woocommerce.shop.json` or `examples/coupang.shop.json` to a local `shop.json`. Enter the actual store name and URL. Coupang also requires the actual vendor ID.

For WooCommerce, create a read/write key under **WooCommerce → Settings → Advanced → REST API**. Image uploads use a WordPress user's **Application Password**, with media upload permission. Coupang also needs a publicly reachable WordPress media library; the first version does not operate WING upload controls.

Supply secrets through local environment variables, never product files or plans:

```powershell
$env:WOO_CONSUMER_KEY = Read-Host 'WooCommerce consumer key'
$env:WOO_CONSUMER_SECRET = Read-Host 'WooCommerce consumer secret'
$env:WP_MEDIA_USER = Read-Host 'WordPress media user'
$passwordInput = Read-Host 'WordPress application password' -AsSecureString
$env:WP_APPLICATION_PASSWORD = [System.Net.NetworkCredential]::new('', $passwordInput).Password
python -m publisher --lang en serve
```

Coupang uses `COUPANG_ACCESS_KEY` and `COUPANG_SECRET_KEY`. Configure API access and allowed IPs according to Coupang's developer-center requirements. This tool does not change store networks or API allowlists.

## Product data

For simple products, use `products.csv`. Chinese headers and their English aliases are supported:

| Chinese header | English alias |
|---|---|
| 商品编码 | sku |
| 商品名称 | title |
| 商品描述 | description |
| 售价 | price |
| 库存 | stock |
| 分类编号 | categories |
| 图片 | images |

Separate image paths and category IDs with semicolons. Image paths are relative to the spreadsheet's folder.

Use a product folder with `product.json` and images for variants. See `examples/商品资料/演示水杯/product.json`. Prices, stock, logistics and qualification data must be actual values. `description_file` can reference a UTF-8 description file in the same product folder.

Coupang additionally needs a `coupang` object with actual category, logistics, returns, qualifications, attributes and disclosure data. Its `items` correspond to variants and `externalVendorSku` must match each variant SKU. See [Coupang data guide](docs/coupang-data.en.md). Store-dependent data is not fabricated by the tool.

## Batch execution

```sh
python -m publisher --lang en plan --source products --shop shop.json --output plans/batch-one --mode draft
python -m publisher --lang en run --plan plans/batch-one
python -m publisher --lang en inspect --plan plans/batch-one
```

`draft` saves drafts. `publish` publishes WooCommerce products or submits Coupang products for review. Before execution, review `发布清单.md` and `plan.json`, including prices, stock, variants and the store.

After execution, read `执行结论.md`, `Summary.en.md` or machine-readable `result.json`. Resolve failures and run the same command again. Product-data changes require a new plan; do not edit an old plan directly. Keep the same runtime folder to retain resumption records.

## Scope

- Product and variant SKUs should be unique in the store. Existing variants absent from your input stop modification; they are not automatically deleted.
- A matching SKU is an actual update target. Check both SKU and store.
- WordPress image URLs must be publicly reachable. Coupang image URLs are limited to 200 characters and must use HTTPS on its default port.
- Up to 500 products per batch and 100 variants per product. Coupang supports up to 10 product images.
- A platform readback that differs from the submitted data is incomplete. Resolve content filtering or field configuration before retrying.
- Naver, Shopify, Cafe24, browser autofill and scheduled execution are not supported.

MIT licensed. Self-host the tool or add adapters for other platforms.

## Contact

Project enquiries and collaboration: [tianchaodaxing@gmail.com](mailto:tianchaodaxing@gmail.com)
