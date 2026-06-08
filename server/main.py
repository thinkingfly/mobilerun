"""Mobilerun Agent Dashboard — 启动入口。"""

import argparse
import logging
import os
import subprocess
import sys


def setup_logging(debug: bool = False):
    """配置日志。"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # 抑制 noisy loggers
    for name in ["httpcore", "httpx", "urllib3", "websockets"]:
        logging.getLogger(name).setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(description="Mobilerun Agent Dashboard")
    parser.add_argument("--port", type=int, default=8080, help="服务端口")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--no-web", action="store_true", help="不启动前端")
    args = parser.parse_args()

    setup_logging(args.debug)

    # 启动 Next.js 开发服务器（后台）
    web_process = None
    if not args.no_web:
        web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
        if os.path.exists(os.path.join(web_dir, "package.json")):
            try:
                print(f"\n  启动 Next.js 开发服务器...")
                web_process = subprocess.Popen(
                    ["npm", "run", "dev"],
                    cwd=web_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                import time

                time.sleep(2)
                print(f"  Next.js 运行在 http://localhost:3000")
            except FileNotFoundError:
                print(f"  警告: npm 未找到，跳过前端启动")

    # 启动 FastAPI
    import uvicorn

    print(f"\n{'=' * 60}")
    print(f"  Mobilerun Agent Dashboard")
    print(f"  API:    http://{args.host}:{args.port}")
    print(f"  端口:   {args.port}")
    print(f"{'=' * 60}\n")

    try:
        uvicorn.run(
            "server.app:app",
            host=args.host,
            port=args.port,
            log_level="debug" if args.debug else "info",
            reload=args.debug,
        )
    finally:
        if web_process:
            web_process.terminate()


if __name__ == "__main__":
    main()
