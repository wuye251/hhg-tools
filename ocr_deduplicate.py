#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信支付截图OCR识别和去重工具
使用tesseract识别订单编号并根据订单编号去重
支持增量OCR，避免重复识别
"""

import re
import subprocess
import shutil
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime

def ocr_image(image_path):
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

def ocr_image_deep(image_path):
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

def extract_order_number(text):
    """从OCR文本中提取订单编号 - 支持跨行识别"""
    # 先尝试常规匹配（单行完整订单号）
    patterns = [
        r'订单号[:：\s]*([0-9A-Za-z]{18,32})',  # 订单号：xxxxxxxx
        r'单号[:：\s]*([0-9A-Za-z]{18,32})',     # 单号：xxxxxxxx
        r'订单编号[:：\s]*([0-9A-Za-z]{18,32})', # 订单编号：xxxxxxxx
        r'商户订单号[:：\s]*([0-9A-Za-z]{18,32})', # 商户订单号
        r'交易单号[:：\s]*([0-9A-Za-z]{18,32})', # 交易单号
        r'\b([0-9]{20,32})\b',                   # 20-32位纯数字
        r'\b([0-9A-Za-z]{24,32})\b',             # 24-32位字母数字
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
    # 处理换行情况：订单号可能被分成两行
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
                        # 提取下一行开头的数字字母
                        next_numbers = re.findall(r'^([0-9A-Za-z]+)', next_line)
                        
                        if next_numbers:
                            # 拼接两行的订单号
                            combined = num + next_numbers[0]
                            # 验证拼接后的长度是否合理
                            if 18 <= len(combined) <= 32:
                                # 过滤日期
                                if not (combined.startswith('2025') or combined.startswith('2024') or combined.startswith('2023')):
                                    return combined
    
    # 还有一种情况：订单号没有关键词，直接从行首开始
    # 查找可能跨行的长数字串
    for i in range(len(lines) - 1):
        line = lines[i].strip()
        next_line = lines[i + 1].strip()
        
        # 先尝试去除行内空格，合并数字段（处理OCR把订单号识别成多个数字的情况）
        # 例如: "4200002791 2025092179555" -> "42000027912025092179555"
        line_no_space = ''.join(re.findall(r'[0-9A-Za-z]+', line))
        
        # 当前行末尾的数字字母（使用去空格后的行）
        end_match = re.search(r'([0-9A-Za-z]{10,})$', line_no_space)
        if end_match:
            end_part = end_match.group(1)
            
            # 下一行开头的数字字母
            start_match = re.search(r'^([0-9A-Za-z]{4,})', next_line)
            if start_match:
                start_part = start_match.group(1)
                
                # 拼接
                combined = end_part + start_part
                
                # 验证拼接后是否是有效订单号
                if 18 <= len(combined) <= 32:
                    # 验证数字占比（订单号通常数字占比高）
                    digit_ratio = sum(c.isdigit() for c in combined) / len(combined)
                    if digit_ratio >= 0.7:  # 至少70%是数字（更严格，避免误识别）
                        # 检查是否以常见的微信订单号开头（4200, 1000等）
                        if combined.startswith('4200') or combined.startswith('1000') or combined.startswith('372'):
                            return combined
                        # 或者不是日期格式
                        elif not (combined.startswith('2025') or combined.startswith('2024') or combined.startswith('2023')):
                            return combined
    
    return None

def extract_amount(text):
    """从OCR文本中提取金额"""
    # 匹配微信支付金额格式
    patterns = [
        r'-(\d+\.\d{2})',  # 负数格式 -123.45
        r'¥(\d+\.\d{2})',  # 带人民币符号
        r'￥(\d+\.\d{2})',  # 全角人民币符号
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return float(matches[0])
    
    # 如果前面的模式都没匹配到，尝试匹配所有带小数点的数字
    all_numbers = re.findall(r'\b(\d+\.\d{2})\b', text)
    if all_numbers:
        valid_amounts = [float(num) for num in all_numbers if 0.01 <= float(num) < 100000]
        if valid_amounts:
            return max(valid_amounts)
    
    return None

def load_cache(cache_file, base_dir):
    """加载已识别的缓存结果（txt格式）"""
    if not cache_file.exists():
        return {}
    
    cache = {}
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # 格式：序号|文件路径|订单号|金额|文件夹|识别时间
                parts = line.split('|')
                if len(parts) >= 5:
                    # parts[0] 是序号，跳过
                    relative_path = parts[1]
                    order_number = parts[2]
                    amount = float(parts[3])
                    folder = parts[4]
                    ocr_time = parts[5] if len(parts) > 5 else ''
                    
                    # 将相对路径转换为绝对路径
                    if relative_path.startswith('/哈哈/'):
                        # 去掉开头的 /哈哈/
                        relative_path = relative_path[4:]
                    full_path = str(base_dir / relative_path)
                    
                    cache[full_path] = {
                        'order_number': order_number,
                        'amount': amount,
                        'folder': folder,
                        'ocr_time': ocr_time
                    }
        
        print(f"✓ 加载缓存: {len(cache)} 条已识别记录")
        return cache
    except Exception as e:
        print(f"✗ 加载缓存失败: {e}")
        return {}

def save_cache(cache_file, cache_data, base_dir):
    """保存识别结果到缓存（txt格式，使用相对路径，带序号）"""
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            # 写入文件头
            f.write("# OCR识别结果缓存\n")
            f.write("# 格式：序号|相对路径|订单号|金额|文件夹|识别时间\n")
            f.write("# 相对路径格式：/哈哈/子文件夹/图片.jpg\n")
            f.write("#" + "="*80 + "\n")
            
            # 写入数据（按路径排序，添加序号）
            for idx, (file_path, data) in enumerate(sorted(cache_data.items()), 1):
                order_number = data['order_number']
                amount = data['amount']
                folder = data.get('folder', '')
                ocr_time = data.get('ocr_time', '')
                
                # 转换为相对路径
                try:
                    path_obj = Path(file_path)
                    relative_path = path_obj.relative_to(base_dir)
                    # 添加 /哈哈/ 前缀
                    relative_path_str = f"/哈哈/{relative_path}"
                except:
                    # 如果无法转换为相对路径，使用原路径
                    relative_path_str = file_path
                
                f.write(f"{idx}|{relative_path_str}|{order_number}|{amount}|{folder}|{ocr_time}\n")
        
        print(f"✓ 缓存已保存: {len(cache_data)} 条记录")
    except Exception as e:
        print(f"✗ 保存缓存失败: {e}")

def backup_cache(cache_file):
    """备份缓存文件"""
    if not cache_file.exists():
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = cache_file.parent / f"ocr_cache_backup_{timestamp}.txt"
    
    try:
        shutil.copy2(cache_file, backup_file)
        print(f"✓ 已备份缓存到: {backup_file.name}")
        return backup_file
    except Exception as e:
        print(f"✗ 备份缓存失败: {e}")
        return None

def find_all_images(base_dir):
    """递归查找所有jpg图片"""
    image_files = []
    base_path = Path(base_dir)
    
    # 递归查找所有jpg和png文件
    for ext in ['*.jpg', '*.JPG', '*.jpeg', '*.JPEG', '*.png', '*.PNG']:
        image_files.extend(base_path.rglob(ext))
    
    return sorted(image_files)

def process_images(image_files, cache=None, incremental=True, debug=False):
    """
    处理所有图片，提取订单号和金额
    
    Args:
        image_files: 图片文件列表
        cache: 缓存字典 {文件路径: {order_number, amount, folder, ocr_time}}
        incremental: 是否增量模式（跳过已识别的）
        debug: 调试模式
    """
    results = []
    failed_files = []
    skipped_count = 0
    
    if cache is None:
        cache = {}
    
    total = len(image_files)
    
    for idx, image_file in enumerate(image_files, 1):
        file_key = str(image_file)
        
        # 增量模式：检查缓存
        if incremental and file_key in cache:
            cached = cache[file_key]
            # 验证缓存的有效性
            if cached.get('order_number') and cached.get('amount'):
                results.append({
                    'file': image_file,
                    'order_number': cached['order_number'],
                    'amount': cached['amount'],
                    'folder': cached.get('folder', image_file.parent.name),
                    'from_cache': True
                })
                skipped_count += 1
                if idx % 50 == 0:  # 每50个显示一次进度
                    print(f"[{idx}/{total}] 已跳过 {skipped_count} 个已识别文件...")
                continue
        
        print(f"[{idx}/{total}] 处理: {image_file.relative_to(image_file.parents[2])}")
        
        # 第一轮：常规OCR
        ocr_text = ocr_image(image_file)
        
        if debug:
            print(f"  → OCR文本预览: {ocr_text[:100].replace(chr(10), ' | ')}")
        
        order_number = extract_order_number(ocr_text)
        amount = extract_amount(ocr_text)
        
        # 如果常规OCR失败，尝试深度OCR
        if order_number is None or amount is None:
            print(f"  → 常规识别失败，尝试深度识别...")
            deep_text = ocr_image_deep(image_file)
            
            # 合并文本以提高识别率
            combined_text = ocr_text + "\n" + deep_text
            
            if order_number is None:
                order_number = extract_order_number(combined_text)
            if amount is None:
                amount = extract_amount(combined_text)
        
        if order_number and amount:
            result = {
                'file': image_file,
                'order_number': order_number,
                'amount': amount,
                'folder': image_file.parent.name,
                'from_cache': False
            }
            results.append(result)
            
            # 更新缓存
            cache[file_key] = {
                'order_number': order_number,
                'amount': amount,
                'folder': image_file.parent.name,
                'ocr_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            print(f"  ✓ 订单号: {order_number} (长度:{len(order_number)}), 金额: ¥{amount:.2f}")
        else:
            failed_files.append(image_file)
            print(f"  ✗ 识别失败 - 订单号: {order_number or '无'}, 金额: {amount or '无'}")
            
            if debug and not order_number:
                lines = ocr_text.split('\n')[:5]
                print(f"  → OCR文本前5行:")
                for line in lines:
                    if line.strip():
                        print(f"     {line.strip()}")
    
    if incremental and skipped_count > 0:
        print(f"\n✓ 增量模式: 跳过了 {skipped_count} 个已识别的文件")
    
    return results, failed_files, cache

def deduplicate_by_order(results):
    """根据订单号去重"""
    unique_orders = {}
    duplicates = defaultdict(list)
    
    for result in results:
        order_num = result['order_number']
        if order_num not in unique_orders:
            unique_orders[order_num] = result
        else:
            # 记录重复的订单
            duplicates[order_num].append(result)
    
    return unique_orders, duplicates

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='微信支付截图OCR识别和去重工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 默认模式（自动判断：有缓存=增量，无缓存=全量）
  python ocr_deduplicate.py
  
  # 清空缓存后重新识别
  python ocr_deduplicate.py --clear-cache
        """
    )
    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='备份并清空缓存，重新识别所有图片'
    )
    parser.add_argument(
        '--copy-dedup',
        action='store_true',
        help='复制去重后的文件到新文件夹（默认不复制）'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='调试模式，显示详细OCR信息'
    )
    
    args = parser.parse_args()
    
    # 获取哈哈文件夹路径
    base_dir = Path(__file__).parent / "哈哈"
    cache_file = base_dir / "ocr_cache.txt"  # 缓存文件放在哈哈文件夹内
    
    if not base_dir.exists():
        print(f"✗ 文件夹不存在: {base_dir}")
        return
    
    print("="*100)
    print("微信支付截图OCR识别和去重工具")
    print("="*100)
    
    # 处理缓存
    cache = {}
    incremental = False
    
    if args.clear_cache:
        # 手动清空缓存：先备份，再清空
        if cache_file.exists():
            backup_cache(cache_file)
            cache_file.unlink()
            print("✓ 已备份并清空缓存\n")
        print(f"运行模式: 全量模式（重新识别所有）\n")
        incremental = False
    elif cache_file.exists():
        # 缓存存在：增量模式
        print(f"运行模式: 增量模式（跳过已识别）\n")
        cache = load_cache(cache_file, base_dir)
        incremental = True
    else:
        # 缓存不存在：全量模式
        print(f"运行模式: 全量模式（首次运行）\n")
        incremental = False
    
    # 查找所有图片
    print(f"\n正在扫描文件夹: {base_dir}")
    image_files = find_all_images(base_dir)
    
    print(f"找到 {len(image_files)} 张图片\n")
    print("="*100)
    print("开始OCR识别...")
    print("="*100)
    print()
    
    # 处理所有图片
    results, failed_files, updated_cache = process_images(
        image_files, 
        cache=cache, 
        incremental=incremental,
        debug=args.debug
    )
    
    # 保存更新后的缓存（增量和全量模式都保存）
    save_cache(cache_file, updated_cache, base_dir)
    
    print("\n" + "="*100)
    print("OCR识别完成")
    print("="*100)
    
    success_count = len(results)
    failed_count = len(failed_files)
    new_ocr_count = len([r for r in results if not r.get('from_cache', False)])
    cached_count = len([r for r in results if r.get('from_cache', False)])
    
    print(f"\n成功识别: {success_count}/{len(image_files)} 张")
    if incremental and cached_count > 0:
        print(f"  - 新识别: {new_ocr_count} 张")
        print(f"  - 缓存读取: {cached_count} 张")
    print(f"识别失败: {failed_count} 张")
    
    if failed_count > 0:
        print(f"\n未识别的图片:")
        for f in failed_files:
            print(f"  - {f.relative_to(base_dir)}")
    
    # 去重
    if results:
        print("\n" + "="*100)
        print("订单去重分析")
        print("="*100)
        
        unique_orders, duplicates = deduplicate_by_order(results)
        
        print(f"\n原始订单数: {len(results)}")
        print(f"唯一订单数: {len(unique_orders)}")
        print(f"重复订单数: {len(duplicates)}")
        
        # 显示重复的订单
        if duplicates:
            print(f"\n检测到 {len(duplicates)} 个重复订单:")
            print("-"*100)
            for order_num, dup_list in duplicates.items():
                original = unique_orders[order_num]
                print(f"\n订单号: {order_num}")
                print(f"  原始文件: {original['file'].relative_to(base_dir)}")
                print(f"  金额: ¥{original['amount']:.2f}")
                print(f"  重复文件 ({len(dup_list)}个):")
                for dup in dup_list:
                    print(f"    - {dup['file'].relative_to(base_dir)}")
        
        # 计算去重后的总金额
        print("\n" + "="*100)
        print("去重后的金额汇总")
        print("="*100)
        
        # 按文件夹分组统计
        folder_stats = defaultdict(lambda: {'count': 0, 'amount': 0})
        
        for order_num, result in sorted(unique_orders.items()):
            folder = result['folder']
            folder_stats[folder]['count'] += 1
            folder_stats[folder]['amount'] += result['amount']
        
        print("\n按文件夹统计:")
        print("-"*100)
        grand_total = 0
        total_count = 0
        
        for folder, stats in sorted(folder_stats.items()):
            print(f"{folder:50s} 订单数: {stats['count']:3d}  金额: ¥{stats['amount']:10.2f}")
            grand_total += stats['amount']
            total_count += stats['count']
        
        print("\n" + "="*100)
        print(f"{'去重后总计':50s} 订单数: {total_count:3d}  金额: ¥{grand_total:10.2f}")
        print("="*100)
        
        # 详细清单
        print("\n详细清单（去重后）:")
        print("-"*100)
        
        for i, (order_num, result) in enumerate(sorted(unique_orders.items(), key=lambda x: x[1]['amount'], reverse=True), 1):
            print(f"{i:3d}. ¥{result['amount']:8.2f}  订单号: {order_num:32s}  文件: {result['file'].name}")
        
        print("\n" + "="*100)
        
        # 根据参数决定是否创建去重后的文件夹并复制文件
        if args.copy_dedup:
            print("\n开始复制去重后的文件...")
            print("="*100)
            
            # 创建新文件夹，使用时间戳命名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dedupe_folder = base_dir.parent / f"去重后的支付截图_{timestamp}"
            dedupe_folder.mkdir(exist_ok=True)
            
            print(f"\n创建文件夹: {dedupe_folder.name}")
            
            # 复制去重后的文件
            copied_count = 0
            for i, (order_num, result) in enumerate(sorted(unique_orders.items(), key=lambda x: x[1]['amount'], reverse=True), 1):
                source_file = result['file']
                # 使用编号_金额_原文件名的格式
                new_filename = f"{i:03d}_¥{result['amount']:.2f}_{source_file.name}"
                dest_file = dedupe_folder / new_filename
                
                try:
                    shutil.copy2(source_file, dest_file)
                    copied_count += 1
                    if i <= 10 or i % 20 == 0:  # 只显示前10个和每20个
                        print(f"  ✓ 复制 [{i}/{len(unique_orders)}]: {new_filename}")
                except Exception as e:
                    print(f"  ✗ 复制失败 [{i}]: {source_file.name} - {e}")
            
            print(f"\n成功复制 {copied_count}/{len(unique_orders)} 个文件到文件夹: {dedupe_folder.name}")
            print(f"文件夹路径: {dedupe_folder}")
            print("="*100)
        else:
            print("\n提示: 使用 --copy-dedup 参数可以复制去重后的文件到新文件夹")
            print("="*100)

if __name__ == "__main__":
    main()

