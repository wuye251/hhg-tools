#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask后端API - 微信支付截图OCR识别和去重
"""

import os
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import threading
import json

from ocr_service import OCRService

app = Flask(__name__)
CORS(app)  # 允许跨域

# 配置
UPLOAD_FOLDER = Path(__file__).parent / 'uploads'
RESULT_FOLDER = Path(__file__).parent / 'results'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'JPG', 'JPEG', 'PNG'}

UPLOAD_FOLDER.mkdir(exist_ok=True)
RESULT_FOLDER.mkdir(exist_ok=True)

# 任务状态存储
tasks = {}

def allowed_file(filename):
    """检查文件是否允许上传"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({'status': 'ok', 'message': 'OCR服务运行中'})

@app.route('/api/upload', methods=['POST'])
def upload_files():
    """上传图片文件"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
        
        files = request.files.getlist('files')
        
        if not files or len(files) == 0:
            return jsonify({'error': '文件列表为空'}), 400
        
        # 创建任务ID
        task_id = str(uuid.uuid4())
        task_folder = UPLOAD_FOLDER / task_id
        task_folder.mkdir(exist_ok=True)
        
        uploaded_files = []
        for i, file in enumerate(files):
            if file and allowed_file(file.filename):
                # 获取相对路径信息（如果前端提供了）
                relative_path = request.form.get(f'file_{i}_path', file.filename)
                print(f"处理文件 {i}: {file.filename}, 路径: {relative_path}")
                
                # 创建目录结构（保留中文字符）
                if '/' in relative_path:
                    # 多级目录
                    dir_parts = relative_path.split('/')
                    filename = dir_parts[-1]  # 不使用secure_filename，保留中文
                    dir_path = task_folder
                    
                    # 创建子目录
                    for dir_part in dir_parts[:-1]:
                        # 对目录名进行安全处理，但保留中文
                        safe_dir_name = dir_part.replace('/', '_').replace('\\', '_')
                        dir_path = dir_path / safe_dir_name
                        dir_path.mkdir(exist_ok=True)
                    
                    # 对文件名进行安全处理，但保留中文
                    safe_filename = filename.replace('/', '_').replace('\\', '_')
                    filepath = dir_path / safe_filename
                else:
                    # 根目录文件
                    safe_filename = file.filename.replace('/', '_').replace('\\', '_')
                    filepath = task_folder / safe_filename
                
                file.save(str(filepath))
                uploaded_files.append(relative_path)
        
        if not uploaded_files:
            shutil.rmtree(task_folder)
            return jsonify({'error': '没有有效的图片文件'}), 400
        
        # 初始化任务状态
        tasks[task_id] = {
            'status': 'uploaded',
            'uploaded_count': len(uploaded_files),
            'created_at': datetime.now().isoformat(),
            'message': f'成功上传 {len(uploaded_files)} 个文件'
        }
        
        return jsonify({
            'task_id': task_id,
            'uploaded_count': len(uploaded_files),
            'message': f'成功上传 {len(uploaded_files)} 个文件'
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/process/<task_id>', methods=['POST'])
def process_task(task_id):
    """开始OCR处理"""
    try:
        if task_id not in tasks:
            return jsonify({'error': '任务不存在'}), 404
        
        if tasks[task_id]['status'] == 'processing':
            return jsonify({'error': '任务正在处理中'}), 400
        
        # 更新任务状态
        tasks[task_id]['status'] = 'processing'
        tasks[task_id]['message'] = '正在处理中...'
        
        # 异步处理OCR
        task_folder = UPLOAD_FOLDER / task_id
        result_folder = RESULT_FOLDER / task_id
        result_folder.mkdir(exist_ok=True)
        
        def process_ocr():
            try:
                ocr_service = OCRService(task_folder, result_folder)
                result = ocr_service.process()
                
                tasks[task_id]['status'] = 'completed'
                tasks[task_id]['result'] = result
                tasks[task_id]['message'] = '处理完成'
                tasks[task_id]['completed_at'] = datetime.now().isoformat()
                
            except Exception as e:
                tasks[task_id]['status'] = 'failed'
                tasks[task_id]['error'] = str(e)
                tasks[task_id]['message'] = f'处理失败: {str(e)}'
        
        thread = threading.Thread(target=process_ocr)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'task_id': task_id,
            'status': 'processing',
            'message': '开始处理'
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/<task_id>', methods=['GET'])
def get_status(task_id):
    """查询任务状态"""
    if task_id not in tasks:
        return jsonify({'error': '任务不存在'}), 404
    
    task = tasks[task_id]
    response = {
        'task_id': task_id,
        'status': task['status'],
        'message': task.get('message', ''),
    }
    
    # 如果处理中，返回进度
    if task['status'] == 'processing' and 'progress' in task:
        response['progress'] = task['progress']
    
    # 如果完成，返回结果摘要
    if task['status'] == 'completed' and 'result' in task:
        result = task['result']
        response['summary'] = {
            'total_files': result.get('total_files', 0),
            'success_count': result.get('success_count', 0),
            'failed_count': result.get('failed_count', 0),
            'unique_orders': result.get('unique_orders', 0),
            'duplicate_orders': result.get('duplicate_orders', 0),
            'total_amount': result.get('total_amount', 0),
        }
    
    return jsonify(response)

@app.route('/api/result/<task_id>', methods=['GET'])
def get_result(task_id):
    """获取处理结果详情"""
    if task_id not in tasks:
        return jsonify({'error': '任务不存在'}), 404
    
    task = tasks[task_id]
    
    if task['status'] != 'completed':
        return jsonify({'error': '任务未完成'}), 400
    
    return jsonify({
        'task_id': task_id,
        'result': task.get('result', {})
    })

@app.route('/api/download/<task_id>', methods=['GET'])
def download_result(task_id):
    """下载去重后的文件（zip格式）"""
    if task_id not in tasks:
        return jsonify({'error': '任务不存在'}), 404
    
    task = tasks[task_id]
    
    if task['status'] != 'completed':
        return jsonify({'error': '任务未完成'}), 400
    
    try:
        result_folder = RESULT_FOLDER / task_id / 'deduped'
        
        if not result_folder.exists():
            return jsonify({'error': '去重文件夹不存在'}), 404
        
        # 创建zip文件
        zip_path = RESULT_FOLDER / task_id / f'deduped_{task_id}.zip'
        shutil.make_archive(
            str(zip_path.with_suffix('')),
            'zip',
            str(result_folder)
        )
        
        return send_file(
            str(zip_path),
            as_attachment=True,
            download_name=f'去重后的支付截图_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        )
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/<task_id>', methods=['GET'])
def download_cache(task_id):
    """下载OCR缓存文件"""
    try:
        task_folder = RESULT_FOLDER / task_id
        cache_file = task_folder / 'ocr_cache.json'
        
        if not cache_file.exists():
            return jsonify({'status': 'error', 'message': '缓存文件不存在'})
        
        return send_file(
            str(cache_file),
            as_attachment=True,
            download_name=f'ocr_cache_{task_id}.json',
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'下载失败: {str(e)}'})

@app.route('/api/cleanup/<task_id>', methods=['DELETE'])
def cleanup_task(task_id):
    """清理任务文件"""
    try:
        if task_id in tasks:
            # 删除上传文件夹
            task_folder = UPLOAD_FOLDER / task_id
            if task_folder.exists():
                shutil.rmtree(task_folder)
            
            # 删除结果文件夹
            result_folder = RESULT_FOLDER / task_id
            if result_folder.exists():
                shutil.rmtree(result_folder)
            
            # 删除任务记录
            del tasks[task_id]
            
            return jsonify({'message': '清理成功'})
        else:
            return jsonify({'error': '任务不存在'}), 404
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
