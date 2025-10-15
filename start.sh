#!/bin/bash

echo "================================"
echo "微信支付截图OCR识别和去重工具"
echo "================================"
echo ""

# 检查 Tesseract 是否安装
if ! command -v tesseract &> /dev/null; then
    echo "❌ 错误: Tesseract OCR 未安装"
    echo ""
    echo "请先安装 Tesseract:"
    echo "  macOS:   brew install tesseract tesseract-lang"
    echo "  Ubuntu:  sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim"
    echo ""
    exit 1
fi

echo "✅ Tesseract OCR 已安装"
tesseract --version | head -n 1
echo ""

# 启动后端
echo "正在启动后端服务..."
cd backend

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "创建 Python 虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "安装 Python 依赖..."
pip install -q -r requirements.txt

# 启动后端
echo "✅ 后端服务启动在 http://localhost:5001"
python app.py &
BACKEND_PID=$!

cd ..

# 启动前端
echo ""
echo "正在启动前端服务..."
cd frontend

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo "安装前端依赖..."
    if command -v yarn &> /dev/null; then
        yarn install
    else
        npm install
    fi
fi

# 启动前端
echo "✅ 前端服务启动在 http://localhost:3000"
if command -v yarn &> /dev/null; then
    yarn dev
else
    npm run dev
fi

# 清理
kill $BACKEND_PID

