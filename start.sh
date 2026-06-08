#!/bin/bash
# Mobilerun Agent Dashboard — 一键启动所有服务
#
# 用法:
#   ./start.sh              # 默认端口 8080
#   ./start.sh --port 9000  # 指定端口
#   ./start.sh --no-web     # 只启动后端
#   ./start.sh --dev        # 开发模式（带 debug）

set -e

cd "$(dirname "$0")"

PORT=8080
DEBUG=""
NO_WEB=""

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)
            PORT="$2"
            shift 2
            ;;
        --debug|--dev)
            DEBUG="--debug"
            shift
            ;;
        --no-web)
            NO_WEB="--no-web"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# 颜色
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Mobilerun Agent Dashboard${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# ── 0. 关闭现有端口上的进程 ──
if lsof -i :$PORT > /dev/null 2>&1; then
    echo -e "${YELLOW}关闭端口 ${PORT} 上的现有进程...${NC}"
    lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
    sleep 1
fi

if [ -z "$NO_WEB" ] && lsof -i :3000 > /dev/null 2>&1; then
    echo -e "${YELLOW}关闭端口 3000 上的现有进程...${NC}"
    lsof -ti :3000 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# ── 1. 检查虚拟环境 ──
if [ ! -d ".venv" ]; then
    echo -e "${RED}错误: 未找到 .venv 虚拟环境${NC}"
    exit 1
fi

source .venv/bin/activate

# ── 2. 检查 mobilerun 是否安装 ──
if ! python -c "import mobilerun" 2>/dev/null; then
    echo -e "${YELLOW}安装 mobilerun...${NC}"
    pip install -e . -q
fi

# ── 3. 启动 Next.js 前端 ──
WEB_PID=""
if [ -z "$NO_WEB" ] && [ -d "web" ] && [ -f "web/package.json" ]; then
    echo -e "${BLUE}[1/3]${NC} 安装前端依赖..."

    if command -v npm &> /dev/null; then
        (cd web && npm install --silent 2>/dev/null)
    elif command -v bun &> /dev/null; then
        (cd web && bun install 2>/dev/null)
    elif command -v pnpm &> /dev/null; then
        (cd web && pnpm install --silent 2>/dev/null)
    else
        echo -e "${YELLOW}  警告: 未找到 npm/bun/pnpm，跳过前端依赖安装${NC}"
    fi

    echo -e "${BLUE}[2/3]${NC} 启动 Next.js 开发服务器..."
    (cd web && npm run dev 2>&1) &
    WEB_PID=$!
    echo -e "  ${GREEN}Next.js → http://localhost:3000${NC} (PID: $WEB_PID)"
    sleep 2
fi

# ── 4. 启动 FastAPI 后端 ──
echo -e "${BLUE}[3/3]${NC} 启动 FastAPI 后端..."
echo -e "  ${GREEN}API     → http://localhost:${PORT}${NC}"
echo -e "  ${GREEN}API 文档→ http://localhost:${PORT}/docs${NC}"
echo ""

# 清理函数
cleanup() {
    echo ""
    echo -e "${YELLOW}正在关闭服务...${NC}"
    if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
        kill "$WEB_PID" 2>/dev/null
        wait "$WEB_PID" 2>/dev/null
    fi
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null
        wait "$SERVER_PID" 2>/dev/null
    fi
    echo -e "${GREEN}已关闭所有服务${NC}"
    exit 0
}

trap cleanup INT TERM

# 启动 uvicorn
uvicorn server.app:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    $DEBUG \
    --log-level debug 2>&1 &
SERVER_PID=$!

# 等待子进程
wait
