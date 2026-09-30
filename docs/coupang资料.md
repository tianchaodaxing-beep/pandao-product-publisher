# Coupang 商品资料

通用资料提供商品名称、图片、售价、库存和规格。`coupang` 对象提供实际店铺、类目和资质资料，采用官方商品创建接口的字段名称。

店铺共有资料可以从已有商品资料复制后逐项核对；不同类目的属性、认证和告知信息不能直接照搬。

以下字段需要填写实际值：

| 字段 | 内容 |
| --- | --- |
| displayCategoryCode | 末级类目编号 |
| saleStartedAt、saleEndedAt | 销售起止时间，格式 `2026-09-30T00:00:00` |
| vendorUserId | 店铺实际 WING 用户标识 |
| deliveryMethod、deliveryCompanyCode | 配送方式和快递公司代码 |
| deliveryChargeType、deliveryCharge | 运费方式和基本运费 |
| freeShipOverAmount、deliveryChargeOnReturn | 包邮门槛和首次退货运费 |
| remoteAreaDeliverable、unionDeliveryType | 偏远地区配送和合并配送设置 |
| returnCenterCode、returnChargeName | 实际退货中心及收件人 |
| companyContactNumber | 实际联系电话 |
| returnZipCode、returnAddress、returnAddressDetail | 实际退货地址 |
| returnCharge、outboundShippingPlaceCode | 退货运费和实际出库地址代码 |
| items | 按商品规格顺序排列的详细资料 |

每个 `items` 项需有 `externalVendorSku`，与通用规格编码一致。还需按官方规范填写 `originalPrice`、`maximumBuyForPerson`、`maximumBuyForPersonPeriod`、`outboundShippingTimeDay`、`unitCount`、`adultOnly`、`taxType`、`parallelImported`、`overseasPurchased`、`pccNeeded`、`attributes`、`notices`、`certifications`、`searchTags`。

工具负责填写 `vendorId`、`sellerProductName`、`itemName`、`salePrice`、`maximumBuyCount`、`images`、`contents` 和 `requested`。其他字段保留资料原值。部分品类还需要官方要求的附加证明或字段，请把它们一并放入 `coupang` 对象。

创建草稿不会提交销售审核。选择发布时，工具提交审核并显示平台返回的真实状态。已经获得销售选项编号的商品，售价和库存通过平台专用接口维护。

资料来源：

- [상품 생성（商品创建）](https://developers.coupangcorp.com/ko/api/products/product-creation)
- [상품 조회（商品查询）](https://developers.coupangcorp.com/ko/api/products/querying-product)
- [상품 요약 정보 조회（按商品编码查询）](https://developers.coupangcorp.com/ko/api/products/query-a-summary-of-product-info)
- [상품 승인 요청（提交商品审核）](https://developers.coupangcorp.com/ko/api/products/request-for-product-approval)
- [상품 아이템별 수량/가격/상태 조회（选项实际库存与售价）](https://developers.coupangcorp.com/ko/api/products/query-quantitypricestatus-by-product-items)

规则以店铺当前权限、类目要求及平台公告为准。
