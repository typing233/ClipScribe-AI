#!/bin/bash
# ClipScribe-AI 启动脚本

set -e

cd "$(dirname "$0")"

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "⚠️  请设置 ANTHROPIC_API_KEY 环境变量："
    echo "   export ANTHROPIC_API_KEY=your-api-key-here"
    echo ""
    echo "如果没有 API key，系统将无法生成解说文案。"
    echo ""
fi

echo "🎬 启动 ClipScribe AI..."
echo "   访问地址: http://localhost:8000"
echo ""

python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
