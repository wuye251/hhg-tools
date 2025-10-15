@echo off
chcp 65001 > nul
echo ================================
echo 微信支付截图OCR识别和去重工具
echo ================================
echo.

:: 检查 Tesseract 是否安装
where tesseract >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ 错误: Tesseract OCR 未安装
    echo.
    echo 请从以下地址下载并安装 Tesseract:
    echo https://github.com/UB-Mannheim/tesseract/wiki
    echo.
    pause
    exit /b 1
)

echo ✅ Tesseract OCR 已安装
tesseract --version | findstr /C:"tesseract"
echo.

:: 启动后端
echo 正在启动后端服务...
cd backend

:: 检查虚拟环境
if not exist "venv" (
    echo 创建 Python 虚拟环境...
    python -m venv venv
)

:: 激活虚拟环境
call venv\Scripts\activate.bat

:: 安装依赖
echo 安装 Python 依赖...
pip install -q -r requirements.txt

:: 启动后端
echo ✅ 后端服务启动在 http://localhost:5001
start "OCR Backend" python app.py

cd ..

:: 启动前端
echo.
echo 正在启动前端服务...
cd frontend

:: 检查 node_modules
if not exist "node_modules" (
    echo 安装前端依赖...
    where yarn >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        yarn install
    ) else (
        npm install
    )
)

:: 启动前端
echo ✅ 前端服务启动在 http://localhost:3000
where yarn >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    yarn dev
) else (
    npm run dev
)

