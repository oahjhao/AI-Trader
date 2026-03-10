#!/bin/bash
# AI-Trader Frontend 本地容器启动脚本
# 端口: 9280

set -e

echo "🚀 AI-Trader Frontend 本地启动脚本"
echo "============================================"

# 配置
IMAGE_NAME="trader-frontend"
CONTAINER_NAME="trader-frontend-local"
HOST_PORT=9280
CONTAINER_PORT=80

# 数据目录映射（使用 /home/admin/.openclaw/data/ai-trader 作为持久化数据）
DATA_DIR="/home/admin/.openclaw/data/ai-trader"
DOCS_DIR="${DATA_DIR}/docs"

# 检查数据目录是否存在
if [ ! -d "$DATA_DIR" ]; then
    echo "❌ 数据目录不存在: $DATA_DIR"
    echo "请确保数据目录已创建"
    exit 1
fi

# 创建必要的子目录
mkdir -p "$DOCS_DIR"

echo "📁 数据目录: $DATA_DIR"
echo "🌐 服务端口: $HOST_PORT"
echo ""

# 检查镜像是否存在，不存在则构建
echo "🔍 检查 Docker 镜像..."
if ! docker images "$IMAGE_NAME" | grep -q "$IMAGE_NAME"; then
    echo "🛠 构建镜像 $IMAGE_NAME..."
    docker build -f Dockerfile.frontend -t "$IMAGE_NAME" .
    echo "✅ 镜像构建完成"
else
    echo "✅ 镜像已存在"
fi
echo ""

# 停止并删除旧容器
echo "🧹 清理旧容器..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
echo ""

# 启动容器
echo "🚀 启动 Frontend 容器..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -p "$HOST_PORT:$CONTAINER_PORT" \
    -v "$DOCS_DIR:/usr/share/nginx/html:ro" \
    -v "$DATA_DIR/data:/usr/share/nginx/html/data:ro" \
    -e TZ=Asia/Shanghai \
    "$IMAGE_NAME"

echo ""
echo "✅ Frontend 服务已启动!"
echo ""
echo "📊 访问地址:"
echo "   - 本地: http://localhost:$HOST_PORT"
echo "   - 外部: http://<服务器IP>:$HOST_PORT"
echo ""
echo "📁 挂载的数据目录:"
echo "   - docs:    $DOCS_DIR -> /usr/share/nginx/html"
echo "   - data:    $DATA_DIR/data -> /usr/share/nginx/html/data"
echo ""
echo "🔧 常用命令:"
echo "   查看日志: docker logs -f $CONTAINER_NAME"
echo "   停止服务: docker stop $CONTAINER_NAME"
echo "   重启服务: docker restart $CONTAINER_NAME"
echo ""
