# Coupang product data

[简体中文](coupang资料.md) · English

Common product data provides title, images, price, stock and variants. The `coupang` object provides the actual store, category and qualification data, using the official product creation API's field names.

You can copy store-wide data from an existing product, then review it field by field. Category-specific attributes, certifications and disclosures must not be copied without checking their applicability.

| Field | Required content |
|---|---|
| displayCategoryCode | Leaf category ID |
| saleStartedAt, saleEndedAt | Sale start and end times, for example `2026-09-30T00:00:00` |
| vendorUserId | Actual store WING user ID |
| deliveryMethod, deliveryCompanyCode | Delivery method and carrier code |
| deliveryChargeType, deliveryCharge | Shipping charge type and base shipping charge |
| freeShipOverAmount, deliveryChargeOnReturn | Free-shipping threshold and initial return shipping charge |
| remoteAreaDeliverable, unionDeliveryType | Remote-area delivery and combined delivery settings |
| returnCenterCode, returnChargeName | Actual return center and recipient |
| companyContactNumber | Actual contact phone number |
| returnZipCode, returnAddress, returnAddressDetail | Actual return address |
| returnCharge, outboundShippingPlaceCode | Return charge and actual shipping origin code |
| items | Detailed data in the same order as the product variants |

Every `items` entry needs `externalVendorSku` matching the common variant SKU. Provide the required official values for `originalPrice`, `maximumBuyForPerson`, `maximumBuyForPersonPeriod`, `outboundShippingTimeDay`, `unitCount`, `adultOnly`, `taxType`, `parallelImported`, `overseasPurchased`, `pccNeeded`, `attributes`, `notices`, `certifications` and `searchTags`.

The tool fills `vendorId`, `sellerProductName`, `itemName`, `salePrice`, `maximumBuyCount`, `images`, `contents` and `requested`. Other supplied fields retain their input values. Some categories need additional evidence or fields; include them in the `coupang` object.

Creating a draft does not submit for sales review. Publishing submits for review and displays the actual returned status. Products with sales option IDs use the platform's dedicated price and stock maintenance APIs.

Official references:

- [Product creation](https://developers.coupangcorp.com/ko/api/products/product-creation)
- [Product query](https://developers.coupangcorp.com/ko/api/products/querying-product)
- [Query by product SKU](https://developers.coupangcorp.com/ko/api/products/query-a-summary-of-product-info)
- [Request product approval](https://developers.coupangcorp.com/ko/api/products/request-for-product-approval)
- [Query option quantity, price and status](https://developers.coupangcorp.com/ko/api/products/query-quantitypricestatus-by-product-items)

Requirements depend on current store permissions, category requirements and platform notices.
