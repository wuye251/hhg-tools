#!/bin/bash
# HHG Tools 云端部署脚本

set -e

echo "🚀 开始部署 HHG Tools..."

# 项目路径
PROJECT_PATH="/opt/hhg-tools"
BACKEND_PATH="$PROJECT_PATH/backend"
FRONTEND_PATH="$PROJECT_PATH/frontend"

# 1. 创建必要目录
echo "📁 创建必要目录..."
sudo mkdir -p $PROJECT_PATH
sudo mkdir -p $BACKEND_PATH/logs
sudo mkdir -p $BACKEND_PATH/uploads
sudo mkdir -p $BACKEND_PATH/results

# 2. 设置权限
echo "🔐 设置权限..."
sudo chown -R www-data:www-data $PROJECT_PATH
sudo chmod -R 755 $PROJECT_PATH

# 3. 部署后端
echo "🔧 部署后端..."
cd $BACKEND_PATH

# 创建虚拟环境
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# 激活虚拟环境并安装依赖
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# 复制配置文件
cp $PROJECT_PATH/deploy/gunicorn.conf.py .
cp $PROJECT_PATH/deploy/ecosystem.config.js .

# 4. 部署前端
echo "🎨 部署前端..."
cd $FRONTEND_PATH

# 安装依赖
npm install

# 构建生产版本
npm run build

# 5. 配置 Nginx
echo "🌐 配置 Nginx..."
sudo cp $PROJECT_PATH/deploy/nginx.conf /etc/nginx/sites-available/hhg-tools
sudo ln -sf /etc/nginx/sites-available/hhg-tools /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# 6. 启动服务
echo "▶️ 启动服务..."
cd $PROJECT_PATH

# 使用 PM2 启动后端
pm2 start ecosystem.config.js
pm2 save
pm2 startup

echo "✅ 部署完成！"
echo "🌐 访问地址: http://your-domain.com"
echo "📊 服务状态: pm2 status"
echo "📝 查看日志: pm2 logs hhg-tools-backend"
