# PANDAO 商品发布工具

把一批商品资料交给工具：处理图片、上传图片库、填写商品与规格、保存草稿或提交发布，最后回读商品编号及平台状态。

支持 **Coupang 韩国站**和 **WooCommerce 独立站**。适合已经有商品资料、需要重复发布或维护商品的团队。工具不调用语言模型，不额外消耗模型额度。

当前版本为 **0.1.0**。真实接口适配已实现，自动检查使用本机接口样例。项目尚未完成生产店铺首个商品验收；接入你的店铺后，请先保存一个真实商品草稿并核对结果。

## 可以完成什么

- 读取多个商品文件夹，或读取一张中文商品表格。
- 将首图和规格图处理为白底 1000 × 1000 图片，其他图片保留比例；不改原图。
- 上传 WordPress 图片库，重复使用已有图片。
- 按商品编码查找原商品，创建新商品或维护已有商品，支持不同规格及规格图片。
- WooCommerce 保存草稿或发布；Coupang 保存草稿或提交审核。
- 逐个回读名称、规格、图片、售价、库存及状态，保存中文结论。
- 单个商品失败后继续其他商品；再次执行时按原商品编码续接。
- 创建请求超时后先查平台。查不到确切结果时停止重复创建，避免生成重复商品。

Coupang 的审核与销售展示由平台决定。工具取得商品编号不代表已经通过审核；平台没有返回公开页面编号时，结果不会生成猜测的商品链接。

## 安装和打开

需要 Python 3.11 或更新版本。

```powershell
python -m pip install -e .
python -m publisher serve
```

Windows 可以双击 `启动商品发布.cmd`。页面只在本机打开。

## 配置店铺

复制 `examples/woocommerce.shop.json` 或 `examples/coupang.shop.json` 为本机的 `shop.json`，填写店铺名称和实际网址。Coupang 还需要填写实际卖家编号。

WooCommerce：在店铺后台 `WooCommerce → Settings（设置）→ Advanced（高级）→ REST API` 创建具有读写权限的密钥。图片上传使用 WordPress 用户的 `Application Passwords（应用密码）`，该用户需要上传媒体权限。Coupang 图片也需要一个可公开访问的 WordPress 图片库；**首版不直接操作 WING 图片上传控件**。

密钥通过本机环境变量提供，不写进商品文件或清单：

```powershell
$env:WOO_CONSUMER_KEY = Read-Host '输入独立站接口密钥'
$env:WOO_CONSUMER_SECRET = Read-Host '输入独立站接口密钥对应的密码'
$env:WP_MEDIA_USER = Read-Host '输入图片库用户名'
$securePassword = Read-Host '输入图片库应用密码' -AsSecureString
$env:WP_APPLICATION_PASSWORD = [System.Net.NetworkCredential]::new('', $securePassword).Password
python -m publisher serve
```

Coupang 将接口密钥分别放入 `COUPANG_ACCESS_KEY`、`COUPANG_SECRET_KEY` 环境变量。API 申请和调用 IP 需按 Coupang 开发者中心要求配置；工具不会切换店铺网络或修改 API 白名单。

## 准备商品资料

简单商品可以使用 `products.csv`。列名为：商品编码、商品名称、商品描述、售价、库存、分类编号、图片。多张图片和多个分类编号用英文分号分隔；图片路径相对于表格所在文件夹。

含规格的商品使用文件夹：

```text
商品资料/
  水杯/
    product.json
    main.jpg
    blue.jpg
  台灯/
    product.json
    main.jpg
```

格式见 `examples/商品资料/演示水杯/product.json`。资料中的售价、库存、物流及资质必须填写真实值。可以用 `description_file` 引用同一商品文件夹里的 UTF-8 详情文字文件。

Coupang 商品还需要 `coupang` 对象，填写实际类目、物流、退货、资质、属性和商品告知信息。其 `items` 与规格逐项对应，`externalVendorSku` 与该规格的商品编码一致。参见 [Coupang 资料说明](docs/coupang资料.md)。这些信息取决于店铺和商品，不会由工具生成虚构值。

## 批量执行

```powershell
python -m publisher plan --source "商品资料" --shop "shop.json" --output "清单/第一批" --mode draft
python -m publisher run --plan "清单/第一批"
python -m publisher inspect --plan "清单/第一批"
```

`draft` 保存草稿；改为 `publish` 时，WooCommerce 发布商品，Coupang 提交审核。执行前核对 `发布清单.md` 和 `plan.json`，包括价格、库存、规格及店铺。

执行后打开 `执行结论.md`，或读取 `result.json`。如果部分商品失败，处理原因后执行同一条 `run` 命令。商品资料变更时生成新清单；不要直接改旧清单。一直使用同一个 `runtime` 文件夹，以保留续接记录。

## 使用范围

- 商品与规格编码应在店铺中保持唯一。现有规格不在资料中时停止修改，不自动删除。
- 原商品编码对应的是实际修改对象，请核对编码和目标店铺。
- WordPress 的图片网址需要可公开访问；Coupang 图片网址最长 200 字，并使用 HTTPS 默认端口。
- 单批最多 500 个商品，单个商品最多 100 个规格。Coupang 最多 10 张商品图。
- 如果平台返回的资料与提交内容不一致，结果显示未完成；需要按错误核对店铺的内容过滤或字段设置。
- 暂未支持 Naver、Shopify、Cafe24、浏览器自动填写和定时运行。

项目使用 MIT 许可证。可自部署，也可为其他平台增加适配。
