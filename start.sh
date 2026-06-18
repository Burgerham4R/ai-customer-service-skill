#!/usr/bin/env bash
# =====================================================================
# conversation-core · 启动脚本（瘦身版 / Phase 3 阶段 5）
#
# 假设：.env 已存在（由 AI 主持收集 Key 并写入；或开发者跑
#       `python scripts/setup-credentials.py` 兜底完成）。
# 仅做四件事：
#   1. 检测 Python ≥ 3.9
#   2. 创建 / 复用 venv（不污染全局环境）
#   3. 安装 / 校验依赖（清华镜像优先，失败 fallback 官方源）
#   4. 启动 FastAPI uvicorn（HTTP；--https 走自签证书）
#
# 用法：
#   ./start.sh                  # HTTP 启动（默认端口 3000）
#   ./start.sh --https          # HTTPS 启动（自签）
#   ./start.sh --rebuild        # 强制重建 venv
#   ./start.sh --port 8080      # 自定义端口
# =====================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CORE_DIR="$SCRIPT_DIR/capabilities/conversation-core"
ENV_FILE="$CORE_DIR/.env"
REQUIREMENTS="$CORE_DIR/requirements.txt"
VENV_DIR="$SCRIPT_DIR/.venv"
MIN_PY_MAJOR=3; MIN_PY_MINOR=9
PORT=3000; REBUILD=0; USE_HTTPS=0

if [ -t 1 ]; then
    GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
else GREEN=''; YELLOW=''; RED=''; CYAN=''; BOLD=''; NC=''; fi
log()  { printf "${CYAN}[%s]${NC} %s\n" "$(date +%H:%M:%S)" "$*"; }
ok()   { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}⚠${NC}  %s\n" "$*"; }
die()  { printf "${RED}✗${NC} %s\n" "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --rebuild) REBUILD=1 ;;
        --https)   USE_HTTPS=1 ;;
        --port)    shift; PORT="$1" ;;
        --help|-h) sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) warn "忽略未知参数: $1" ;;
    esac
    shift
done

# ---------------- Step 1: 前置检查 ----------------
[ -f "$ENV_FILE" ] || die ".env 不存在: $ENV_FILE\n  请先在 Coding Agent 中按 SKILL.md §7 完成三把 Key 配置；\n  或开发者兜底：python3 scripts/setup-credentials.py"

PY_CMD=""
for cand in python3.12 python3.11 python3.10 python3.9 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        VER=$("$cand" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
        MAJOR=$(echo "$VER" | cut -d. -f1); MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "$MAJOR" -gt "$MIN_PY_MAJOR" ] || { [ "$MAJOR" -eq "$MIN_PY_MAJOR" ] && [ "$MINOR" -ge "$MIN_PY_MINOR" ]; }; then
            PY_CMD="$cand"; ok "Python $VER -> $(command -v "$cand")"; break
        fi
    fi
done
[ -z "$PY_CMD" ] && die "未检测到 Python ≥ ${MIN_PY_MAJOR}.${MIN_PY_MINOR}"

# ---------------- Step 2: venv ----------------
[ "$REBUILD" -eq 1 ] && [ -d "$VENV_DIR" ] && { warn "重建 venv..."; rm -rf "$VENV_DIR"; }
NEED_INSTALL=0
if [ ! -d "$VENV_DIR" ]; then
    log "创建虚拟环境..."
    "$PY_CMD" -m venv "$VENV_DIR" || die "venv 创建失败（Linux 可能需 apt install python3-venv）"
    NEED_INSTALL=1
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
VENV_PY="$VENV_DIR/bin/python"; VENV_PIP="$VENV_DIR/bin/pip"

# ---------------- Step 3: 依赖 ----------------
[ "$NEED_INSTALL" -eq 0 ] && ! "$VENV_PY" -c "import fastapi, uvicorn, requests, dotenv, pydantic" 2>/dev/null && NEED_INSTALL=1
if [ "$NEED_INSTALL" -eq 1 ]; then
    log "安装依赖..."
    "$VENV_PIP" install --upgrade pip >/dev/null 2>&1 || true
    if "$VENV_PIP" install -r "$REQUIREMENTS" -i "https://pypi.tuna.tsinghua.edu.cn/simple" --timeout 15 >/dev/null 2>&1; then
        ok "依赖安装完成（清华镜像）"
    else
        warn "镜像源失败，切换官方源..."
        "$VENV_PIP" install -r "$REQUIREMENTS" >/dev/null || die "依赖安装失败"
        ok "依赖安装完成（官方源）"
    fi
else ok "依赖已就绪"; fi

# ---------------- Step 4: 启动 ----------------
SSL_ARGS=""
if [ "$USE_HTTPS" -eq 1 ]; then
    CERT_DIR="$SCRIPT_DIR/certs"; CERT_FILE="$CERT_DIR/cert.pem"; KEY_FILE="$CERT_DIR/key.pem"
    if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
        command -v openssl >/dev/null 2>&1 || die "openssl 未安装"
        mkdir -p "$CERT_DIR"
        openssl req -x509 -newkey rsa:2048 -nodes -keyout "$KEY_FILE" -out "$CERT_FILE" \
            -days 365 -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" 2>/dev/null
        ok "自签证书已生成"
    fi
    SSL_ARGS="--ssl-keyfile $KEY_FILE --ssl-certfile $CERT_FILE"
fi

SCHEME="http"; [ "$USE_HTTPS" -eq 1 ] && SCHEME="https"
printf "%b🚀 启动 conversation-core: %s://localhost:%s%b (Ctrl+C 停止)\n" "$GREEN" "$SCHEME" "$PORT" "$NC"

cd "$CORE_DIR"
export HOST="${HOST:-0.0.0.0}"; export PORT="$PORT"
# shellcheck disable=SC2086
exec "$VENV_PY" -m uvicorn src.server:app --host "$HOST" --port "$PORT" $SSL_ARGS
