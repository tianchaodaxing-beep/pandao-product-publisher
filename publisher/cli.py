import argparse
from .i18n import Parser, configure, t, write_summary
import json
import sys
from pathlib import Path
from . import __version__
from .common import PublishError
from .plan import build_plan, load_plan
from .engine import run_plan


def main(argv=None):
    argv = configure(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = Parser(description="PANDAO 商品发布工具")
    parser.add_argument("--lang", choices=["zh", "en"], default="zh", help="Display language: zh or en")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="生成可核对的商品发布清单")
    plan.add_argument("--source", required=True)
    plan.add_argument("--shop", required=True)
    plan.add_argument("--output", required=True)
    plan.add_argument("--mode", choices=["draft", "publish"], default="draft")
    run = sub.add_parser("run", help="按清单执行上传并核对平台结果")
    run.add_argument("--plan", required=True)
    run.add_argument("--runtime", default="runtime")
    inspect = sub.add_parser("inspect", help="读取批次商品结果")
    inspect.add_argument("--plan", required=True)
    serve = sub.add_parser("serve", help="打开本机商品发布页面")
    serve.add_argument("--port", type=int, default=18736)
    serve.add_argument("--runtime", default="runtime")
    serve.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = build_plan(args.source, args.shop, args.output, args.mode)
            print(t(f"已生成清单：{len(result['products'])} 个商品；目标店铺：{result['shop']['name']}"))
            print(str(Path(args.output).resolve() / "发布清单.md"))
        elif args.command == "run":
            report = run_plan(args.plan, args.runtime)
            print(t(f"已完成核对 {report['passed']} / {report['total']} 个商品；失败 {report['failed']} 个"))
            print(str(Path(args.plan).resolve() / "执行结论.md"))
            return 0 if report["complete"] else 2
        elif args.command == "inspect":
            load_plan(args.plan)
            result = Path(args.plan) / "result.json"
            if not result.exists():
                raise PublishError("这批清单尚未执行")
            print(result.read_text(encoding="utf-8"))
        else:
            from .server import serve
            serve(args.port, args.runtime, not args.no_browser)
        return 0
    except PublishError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(t("已停止；已取得的商品编号会在下一次执行时核对。"), file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
