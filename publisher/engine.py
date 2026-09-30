import datetime
import time
import traceback
from pathlib import Path
from .common import PublishError, digest, exclusive, write_json
from .plan import load_plan
from .state import State
from .media import WordPressMedia
from .woocommerce import WooCommerce
from .coupang import Coupang


def run_plan(folder, runtime, sleeper=time.sleep):
    folder, runtime = Path(folder).resolve(), Path(runtime).resolve()
    plan = load_plan(folder)
    config = plan["shop"]
    # 对店铺物理地址绑定锁和记录，换环境变量名称不会创建另一个店铺身份。
    identity = {"platform": config["platform"], "target": config.get("url", config.get("vendor_id")).rstrip("/")}
    namespace = digest(identity)
    results = []
    with exclusive(runtime / (namespace + ".lock")):
        state = State(runtime / "state.sqlite")
        try:
            adapter = WooCommerce(config, state, namespace, sleeper) if config["platform"] == "woocommerce" else Coupang(config, state, namespace, sleeper)
            media = WordPressMedia(config, state, folder, digest(config["media"]["url"]), sleeper)
            for product in plan["products"]:
                started = datetime.datetime.now().astimezone().isoformat()
                try:
                    assets = {"images": [media.upload(i) for i in product["images"]], "variants": {}}
                    for variant in product["variants"]:
                        if variant.get("image"):
                            assets["variants"][variant["sku"]] = media.upload(variant["image"])
                    result = {"sku": product["sku"], "title": product["title"], "started_at": started,
                              "ok": True, **adapter.publish(product, assets, plan["mode"])}
                except PublishError as exc:
                    result = {"sku": product["sku"], "title": product["title"], "started_at": started,
                              "ok": False, "verified": False, "status": "未完成", "error": str(exc)}
                except Exception as exc:
                    # 非预期故障保留本机完整堆栈，并继续独立商品；不伪造成功。
                    runtime.mkdir(parents=True, exist_ok=True)
                    with (runtime / "错误记录.log").open("a", encoding="utf-8") as handle:
                        handle.write(datetime.datetime.now().isoformat() + " " + product["sku"] + "\n")
                        traceback.print_exc(file=handle)
                    result = {"sku": product["sku"], "title": product["title"], "started_at": started,
                              "ok": False, "verified": False, "status": "未完成",
                              "error": f"执行失败（{type(exc).__name__}），请查看本机错误记录.log"}
                results.append(result)
                write_json(folder / "result.json", summarize(plan, results))
        finally:
            state.close()
    report = summarize(plan, results)
    write_json(folder / "result.json", report)
    rows = ["# 商品执行结果", "", f"店铺：{config['name']}", f"完成核对：{report['passed']} / {report['total']} 个商品", ""]
    for result in results:
        rows.append(f"- {result['sku']}：{result['status']}" + (f"；商品编号 {result['id']}" if result.get("id") else ""))
        if result.get("url"):
            rows.append("  商品地址：" + result["url"])
        if result.get("error"):
            rows.append("  处理方法：" + result["error"])
    (folder / "执行结论.md").write_text("\n".join(rows), encoding="utf-8")
    return report


def summarize(plan, results):
    total = len(plan["products"])
    passed = sum(r["ok"] and r["verified"] for r in results)
    return {"shop": plan["shop"]["name"], "platform": plan["shop"]["platform"], "mode": plan["mode"],
            "plan_digest": plan["digest"], "time": datetime.datetime.now().astimezone().isoformat(),
            "total": total, "processed": len(results), "passed": passed,
            "failed": sum(not r["ok"] for r in results), "complete": len(results) == total and passed == total,
            "results": results}
