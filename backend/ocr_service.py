#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR服务 - 从ocr_deduplicate.py改造而来
"""

import re
import subprocess
import shutil
import hashlib
import json
import concurrent.futures
from pathlib import Path
from collections import defaultdict
from datetime import datetime

class OCRService:
    def __init__(self, source_folder, result_folder):
        self.source_folder = Path(source_folder)
        self.result_folder = Path(result_folder)
        self.deduped_folder = self.result_folder / 'deduped'
        self.deduped_folder.mkdir(exist_ok=True)
        
        # 缓存文件路径
        self.cache_file = self.result_folder / 'ocr_cache.json'
        self.cache = self.load_cache()
    
    def get_file_fingerprint(self, file_path):
        """生成文件指纹（路径+大小+修改时间）"""
        try:
            stat = file_path.stat()
            relative_path = str(file_path.relative_to(self.source_folder))
            fingerprint = f"{relative_path}:{stat.st_size}:{stat.st_mtime}"
            return hashlib.md5(fingerprint.encode()).hexdigest()
        except:
            return None
    
    def load_cache(self):
        """加载OCR缓存"""
        if not self.cache_file.exists():
            return {}
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                print(f"✓ 加载缓存: {len(cache)} 条记录")
                return cache
        except Exception as e:
            print(f"✗ 加载缓存失败: {e}")
            return {}
    
    def save_cache(self):
        """保存OCR缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
                print(f"✓ 缓存已保存: {len(self.cache)} 条记录")
        except Exception as e:
            print(f"✗ 保存缓存失败: {e}")
    
    def is_cached(self, file_path):
        """检查文件是否已缓存"""
        fingerprint = self.get_file_fingerprint(file_path)
        if not fingerprint:
            return False
        
        if fingerprint in self.cache:
            cached_data = self.cache[fingerprint]
            # 验证缓存数据的完整性
            if all(key in cached_data for key in ['order_number', 'amount', 'folder', 'relative_path', 'ocr_time']):
                return True
        
        return False
    
    def get_cached_result(self, file_path):
        """获取缓存的识别结果"""
        fingerprint = self.get_file_fingerprint(file_path)
        if fingerprint and fingerprint in self.cache:
            return self.cache[fingerprint]
        return None
    
    def cache_result(self, file_path, order_number, amount, folder, relative_path):
        """缓存识别结果"""
        fingerprint = self.get_file_fingerprint(file_path)
        if fingerprint:
            self.cache[fingerprint] = {
                'order_number': order_number,
                'amount': amount,
                'folder': folder,
                'relative_path': relative_path,
                'ocr_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    def get_file_hash(self, file_path):
        """计算文件的MD5哈希值"""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            print(f"计算文件哈希失败: {file_path} - {e}")
            return None
    
    def ocr_image(self, image_path):
        """使用tesseract识别图片文字"""
        try:
            result = subprocess.run(
                ['tesseract', str(image_path), 'stdout', '-l', 'chi_sim+eng'],
                capture_output=True,
                text=True,
                timeout=15
            )
            return result.stdout
        except:
            # 如果中文失败，尝试仅英文
            try:
                result = subprocess.run(
                    ['tesseract', str(image_path), 'stdout'],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                return result.stdout
            except Exception as e:
                return ""
    
    def ocr_image_deep(self, image_path):
        """深度OCR - 使用多种PSM模式"""
        texts = []
        
        # 尝试不同的PSM模式
        for psm in ['6', '11', '12']:
            try:
                result = subprocess.run(
                    ['tesseract', str(image_path), 'stdout', '--psm', psm],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                texts.append(result.stdout)
            except:
                pass
        
        return "\n".join(texts)
    
    def extract_order_number(self, text):
        """从OCR文本中提取订单编号 - 支持跨行识别"""
        # 先尝试常规匹配（单行完整订单号）
        patterns = [
            r'订单号[:：\s]*([0-9A-Za-z]{18,32})',
            r'单号[:：\s]*([0-9A-Za-z]{18,32})',
            r'订单编号[:：\s]*([0-9A-Za-z]{18,32})',
            r'商户订单号[:：\s]*([0-9A-Za-z]{18,32})',
            r'交易单号[:：\s]*([0-9A-Za-z]{18,32})',
            r'\b([0-9]{20,32})\b',
            r'\b([0-9A-Za-z]{24,32})\b',
        ]
        
        # 首先尝试常规单行匹配
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                order_num = matches[0].strip()
                # 过滤掉一些常见的误识别（如日期、时间等）
                if len(order_num) >= 18 and not order_num.startswith('2025') and not order_num.startswith('2024'):
                    return order_num
        
        # 如果单行匹配失败，尝试跨行拼接
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            # 查找包含"订单号"等关键词的行
            if re.search(r'订单号|单号|订单编号|商户订单号|交易单号', line, re.IGNORECASE):
                # 提取当前行的数字字母部分
                current_line_numbers = re.findall(r'[:：\s]*([0-9A-Za-z]+)', line)
                
                # 如果当前行有数字，且长度不够（可能被截断）
                for num in current_line_numbers:
                    if len(num) >= 10 and len(num) < 32:
                        # 检查下一行是否有继续的数字
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            next_numbers = re.findall(r'^([0-9A-Za-z]+)', next_line)
                            
                            if next_numbers:
                                # 拼接两行的订单号
                                combined = num + next_numbers[0]
                                # 验证拼接后的长度是否合理
                                if 18 <= len(combined) <= 32:
                                    if not (combined.startswith('2025') or combined.startswith('2024') or combined.startswith('2023')):
                                        return combined
        
        # 查找可能跨行的长数字串
        for i in range(len(lines) - 1):
            line = lines[i].strip()
            next_line = lines[i + 1].strip()
            
            line_no_space = ''.join(re.findall(r'[0-9A-Za-z]+', line))
            
            end_match = re.search(r'([0-9A-Za-z]{10,})$', line_no_space)
            if end_match:
                end_part = end_match.group(1)
                
                start_match = re.search(r'^([0-9A-Za-z]{4,})', next_line)
                if start_match:
                    start_part = start_match.group(1)
                    
                    combined = end_part + start_part
                    
                    if 18 <= len(combined) <= 32:
                        digit_ratio = sum(c.isdigit() for c in combined) / len(combined)
                        if digit_ratio >= 0.7:
                            if combined.startswith('4200') or combined.startswith('1000') or combined.startswith('372'):
                                return combined
                            elif not (combined.startswith('2025') or combined.startswith('2024') or combined.startswith('2023')):
                                return combined
        
        return None
    
    def extract_amount(self, text):
        """从OCR文本中提取金额"""
        patterns = [
            r'-(\d+\.\d{2})',
            r'¥(\d+\.\d{2})',
            r'￥(\d+\.\d{2})',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                return float(matches[0])
        
        all_numbers = re.findall(r'\b(\d+\.\d{2})\b', text)
        if all_numbers:
            valid_amounts = [float(num) for num in all_numbers if 0.01 <= float(num) < 100000]
            if valid_amounts:
                return max(valid_amounts)
        
        return None
    
    def process_single_image(self, image_file):
        """处理单个图片（用于并发处理）"""
        try:
            # 检查是否为重复文件
            file_hash = self.get_file_hash(image_file)
            is_duplicate = file_hash in self.duplicate_files
            
            # 计算相对路径，保持文件夹结构
            try:
                relative_path = image_file.relative_to(self.source_folder)
                folder_path = str(relative_path.parent) if relative_path.parent != Path('.') else '根目录'
                display_name = str(relative_path)
            except:
                folder_path = image_file.parent.name
                display_name = image_file.name
            
            if is_duplicate:
                return {'type': 'duplicate', 'file': image_file, 'display_name': display_name}
            
            # 检查缓存
            if self.is_cached(image_file):
                cached_result = self.get_cached_result(image_file)
                if cached_result:
                    print(f"✓ 使用缓存: {display_name}")
                    return {
                        'type': 'cached',
                        'file': image_file,
                        'order_number': cached_result['order_number'],
                        'amount': cached_result['amount'],
                        'folder': cached_result['folder'],
                        'relative_path': cached_result['relative_path'],
                        'display_name': display_name
                    }
            
            # 进行OCR识别
            print(f"🔍 OCR识别: {display_name}")
            
            # 第一轮：常规OCR
            ocr_text = self.ocr_image(image_file)
            
            order_number = self.extract_order_number(ocr_text)
            amount = self.extract_amount(ocr_text)
            
            # 如果常规OCR失败，尝试深度OCR
            if order_number is None or amount is None:
                print(f"  → 常规识别失败，尝试深度识别...")
                deep_text = self.ocr_image_deep(image_file)
                
                combined_text = ocr_text + "\n" + deep_text
                
                if order_number is None:
                    order_number = self.extract_order_number(combined_text)
                if amount is None:
                    amount = self.extract_amount(combined_text)
            
            if order_number and amount:
                # 缓存结果
                self.cache_result(image_file, order_number, amount, folder_path, display_name)
                
                print(f"  ✓ 订单号: {order_number} (长度:{len(order_number)}), 金额: ¥{amount:.2f}")
                return {
                    'type': 'success',
                    'file': image_file,
                    'order_number': order_number,
                    'amount': amount,
                    'folder': folder_path,
                    'relative_path': display_name,
                    'display_name': display_name
                }
            else:
                print(f"  ✗ 识别失败 - 订单号: {order_number or '无'}, 金额: {amount or '无'}")
                return {'type': 'failed', 'file': image_file, 'display_name': display_name}
                
        except Exception as e:
            print(f"  ✗ 处理异常: {image_file.name} - {e}")
            return {'type': 'error', 'file': image_file, 'error': str(e)}
    
    def find_all_images(self):
        """递归查找所有图片，保持文件夹结构"""
        image_files = []
        
        for ext in ['*.jpg', '*.JPG', '*.jpeg', '*.JPEG', '*.png', '*.PNG']:
            image_files.extend(self.source_folder.rglob(ext))
        
        return sorted(image_files)
    
    def process_images(self, image_files):
        """处理所有图片，提取订单号和金额，同时检测重复（支持缓存和并发）"""
        results = []
        failed_files = []
        duplicate_files = {}  # {hash: [file1, file2, ...]}
        
        total = len(image_files)
        
        # 第一步：计算所有文件的哈希值，检测重复
        print("正在检测重复文件...")
        file_hashes = {}
        for image_file in image_files:
            file_hash = self.get_file_hash(image_file)
            if file_hash:
                if file_hash in file_hashes:
                    if file_hash not in duplicate_files:
                        duplicate_files[file_hash] = [file_hashes[file_hash]]
                    duplicate_files[file_hash].append(image_file)
                    print(f"发现重复文件: {image_file.name}")
                else:
                    file_hashes[file_hash] = image_file
        
        self.duplicate_files = duplicate_files
        
        # 第二步：并发处理非重复文件
        print("开始并发OCR识别...")
        non_duplicate_files = []
        for image_file in image_files:
            file_hash = self.get_file_hash(image_file)
            if file_hash not in duplicate_files:
                non_duplicate_files.append(image_file)
        
        print(f"总文件数: {len(image_files)} 个")
        print(f"需要处理的文件: {len(non_duplicate_files)} 个")
        print(f"重复文件组: {len(duplicate_files)} 组")
        print(f"重复文件总数: {sum(len(files) for files in duplicate_files.values())} 个")
        
        # 详细显示重复文件信息
        if duplicate_files:
            print("重复文件详情:")
            for hash_val, files in duplicate_files.items():
                print(f"  哈希 {hash_val[:8]}...: {[f.name for f in files]}")
        
        # 使用线程池并发处理
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # 提交所有任务
            future_to_file = {executor.submit(self.process_single_image, img): img for img in non_duplicate_files}
            
            # 收集结果
            processed_count = 0
            cached_count = 0
            for future in concurrent.futures.as_completed(future_to_file):
                processed_count += 1
                result = future.result()
                
                if result['type'] == 'success':
                    results.append({
                        'file': result['file'],
                        'order_number': result['order_number'],
                        'amount': result['amount'],
                        'folder': result['folder'],
                        'relative_path': result['relative_path'],
                    })
                elif result['type'] == 'cached':
                    cached_count += 1
                    results.append({
                        'file': result['file'],
                        'order_number': result['order_number'],
                        'amount': result['amount'],
                        'folder': result['folder'],
                        'relative_path': result['relative_path'],
                    })
                elif result['type'] == 'failed':
                    failed_files.append(result['file'])
                elif result['type'] == 'error':
                    failed_files.append(result['file'])
                
                # 显示进度
                if processed_count % 10 == 0 or processed_count == len(non_duplicate_files):
                    print(f"进度: {processed_count}/{len(non_duplicate_files)} (缓存: {cached_count})")
        
        # 保存缓存
        self.save_cache()
        
        # 处理重复文件信息
        duplicate_info = []
        for file_hash, files in duplicate_files.items():
            duplicate_info.append({
                'hash': file_hash,
                'files': [str(f.relative_to(self.source_folder)) if f.parent != self.source_folder else f.name for f in files],
                'count': len(files)
            })
        
        print(f"处理完成: 成功 {len(results)}, 失败 {len(failed_files)}, 缓存 {cached_count}")
        
        return results, failed_files, duplicate_info
    
    def deduplicate_by_order(self, results):
        """根据订单号去重"""
        unique_orders = {}
        duplicates = defaultdict(list)
        
        for result in results:
            order_num = result['order_number']
            if order_num not in unique_orders:
                unique_orders[order_num] = result
            else:
                duplicates[order_num].append(result)
        
        return unique_orders, duplicates
    
    def process(self):
        """主处理流程"""
        print(f"开始处理文件夹: {self.source_folder}")
        
        # 查找所有图片
        image_files = self.find_all_images()
        total_files = len(image_files)
        
        print(f"找到 {total_files} 张图片")
        
        if total_files == 0:
            return {
                'total_files': 0,
                'success_count': 0,
                'failed_count': 0,
                'error': '未找到图片文件'
            }
        
        # 处理所有图片（包含重复检测）
        results, failed_files, duplicate_info = self.process_images(image_files)
        
        success_count = len(results)
        failed_count = len(failed_files)
        
        # 去重
        unique_orders = {}
        duplicates = {}
        total_amount = 0
        
        if results:
            unique_orders, duplicates = self.deduplicate_by_order(results)
            
            # 计算总金额
            for order_num, result in unique_orders.items():
                total_amount += result['amount']
            
            # 复制去重后的文件，保持文件夹结构
            for i, (order_num, result) in enumerate(sorted(unique_orders.items(), key=lambda x: x[1]['amount'], reverse=True), 1):
                source_file = result['file']
                folder_path = result.get('folder', '根目录')
                relative_path = result.get('relative_path', source_file.name)
                
                # 创建目标文件夹
                dest_folder = self.deduped_folder
                if folder_path != '根目录':
                    dest_folder = dest_folder / folder_path
                    dest_folder.mkdir(parents=True, exist_ok=True)
                
                # 生成新文件名
                new_filename = f"{i:03d}_¥{result['amount']:.2f}_{source_file.name}"
                dest_file = dest_folder / new_filename
                
                try:
                    shutil.copy2(source_file, dest_file)
                except Exception as e:
                    print(f"复制文件失败: {source_file.name} - {e}")
        
        # 计算重复文件统计
        total_duplicate_files = sum(info['count'] for info in duplicate_info)
        
        # 准备返回结果
        result_data = {
            'total_files': total_files,
            'success_count': success_count,
            'failed_count': failed_count,
            'unique_orders': len(unique_orders),
            'duplicate_orders': len(duplicates),
            'duplicate_images': len(duplicate_info),
            'total_duplicate_files': total_duplicate_files,
            'total_amount': round(total_amount, 2),
            'orders': [],
            'duplicates': [],
            'duplicate_images_list': duplicate_info,
            'failed_files': [f.name for f in failed_files]
        }
        
        # 详细订单列表
        for i, (order_num, result) in enumerate(sorted(unique_orders.items(), key=lambda x: x[1]['amount'], reverse=True), 1):
            result_data['orders'].append({
                'index': i,
                'order_number': order_num,
                'amount': result['amount'],
                'filename': result['file'].name,
                'folder': result['folder'],
                'relative_path': result.get('relative_path', result['file'].name)
            })
        
        # 重复订单列表
        for order_num, dup_list in duplicates.items():
            original = unique_orders[order_num]
            result_data['duplicates'].append({
                'order_number': order_num,
                'amount': original['amount'],
                'original_file': original['file'].name,
                'duplicate_files': [dup['file'].name for dup in dup_list],
                'duplicate_count': len(dup_list)
            })
        
        # 重复图片列表已经在duplicate_info中处理，不需要额外处理
        
        print(f"处理完成: 成功 {success_count}, 失败 {failed_count}, 唯一订单 {len(unique_orders)}")
        
        return result_data

