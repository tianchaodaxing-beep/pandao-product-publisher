import csv
import tempfile
import unittest
from pathlib import Path
from publisher.common import PublishError
from publisher.plan import load_products
from publisher import i18n


class LanguageTests(unittest.TestCase):
    def test_csv_headers_are_equivalent_and_values_are_preserved(self):
        values = ["SKU-中文", "商品名称", "<p>描述</p>", "19.90", "3", "11;12", "主图.png;图二.png"]
        headers = [["商品编码", "商品名称", "商品描述", "售价", "库存", "分类编号", "图片"],
                   ["sku", "title", "description", "price", "stock", "categories", "images"]]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            outputs = []
            for names in headers:
                with (folder / "products.csv").open("w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(names)
                    writer.writerow(values)
                outputs.append(load_products(folder)[0][1])
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[1]["title"], "商品名称")
            self.assertEqual(outputs[1]["images"], ["主图.png", "图二.png"])

    def test_conflicting_header_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "products.csv").write_text("商品编码,sku\n甲,乙\n", encoding="utf-8")
            with self.assertRaisesRegex(PublishError, "中英文列值不同"):
                load_products(folder)

    def test_language_option_does_not_consume_command_arguments(self):
        result = i18n.configure(["--lang", "en", "run", "--", "python", "--lang", "zh"])
        self.assertEqual(result, ["run", "--", "python", "--lang", "zh"])
        i18n.configure(["--lang", "zh"])
