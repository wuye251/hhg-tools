#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信支付截图OCR识别工具 - 批量文件夹处理
自动识别多个文件夹中的微信支付截图金额并求和
"""

import re
import subprocess
from pathlib import Path

def ocr_image(image_path):
    """使用tesseract识别图片文字"""
    try:
        result = subprocess.run(
            ['tesseract', image_path, 'stdout', '-l', 'chi_sim+eng'],
            capture_output=True,
            text=True,
            timeout=15
        )
        return result.stdout
    except:
        # 如果中文失败，尝试仅英文
        try:
            result = subprocess.run(
                ['tesseract', image_path, 'stdout'],
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
                ['tesseract', image_path, 'stdout', '--psm', psm],
                capture_output=True,
                text=True,
                timeout=15
            )
            texts.append(result.stdout)
        except:
            pass
    
    return "\n".join(texts)

def extract_amount(text):
    """从OCR文本中提取金额"""
    # 匹配微信支付金额格式
    patterns = [
        r'-(\d+\.\d{2})',  # 负数格式 -123.45
        r'¥(\d+\.\d{2})',  # 带人民币符号
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return float(matches[0])
    
    # 如果前面的模式都没匹配到，尝试匹配所有带小数点的数字
    all_numbers = re.findall(r'\b(\d+\.\d{2})\b', text)
    if all_numbers:
        valid_amounts = [float(num) for num in all_numbers if float(num) < 10000]
        if valid_amounts:
            return max(valid_amounts)
    
    return None

def process_folder(folder_path, expected_amount):
    """处理单个文件夹中的所有图片"""
    # 获取所有jpg图片
    image_files = sorted(folder_path.glob("*.jpg"))
    
    if not image_files:
        print(f"  未找到任何jpg图片文件")
        return None, []
    
    print(f"  找到 {len(image_files)} 张图片，开始识别...\n")
    
    amounts = []
    failed_files = []
    
    # 第一轮：常规识别
    for image_file in image_files:
        print(f"  处理: {image_file.name}")
        
        ocr_text = ocr_image(str(image_file))
        amount = extract_amount(ocr_text)
        
        if amount is not None:
            amounts.append((image_file.name, amount))
            print(f"    ✓ 识别到金额: ¥{amount:.2f}")
        else:
            failed_files.append(image_file)
            print(f"    ✗ 未能识别金额（将使用深度识别）")
    
    # 第二轮：深度识别失败的图片
    if failed_files:
        print(f"\n  {'='*76}")
        print(f"  深度识别 {len(failed_files)} 张失败的图片...")
        print(f"  {'='*76}\n")
        
        for image_file in failed_files:
            print(f"  深度处理: {image_file.name}")
            
            deep_text = ocr_image_deep(str(image_file))
            amount = extract_amount(deep_text)
            
            if amount is not None:
                amounts.append((image_file.name, amount))
                print(f"    ✓ 识别到金额: ¥{amount:.2f}")
            else:
                print(f"    ✗ 仍然无法识别")
    
    return amounts, image_files

def print_folder_summary(folder_name, amounts, image_files, expected_amount):
    """打印单个文件夹的识别结果摘要"""
    print(f"\n  {'='*76}")
    print(f"  识别结果汇总")
    print(f"  {'='*76}")
    
    success_count = len(amounts)
    failed_count = len(image_files) - success_count
    
    print(f"\n  成功识别: {success_count}/{len(image_files)} 张")
    if failed_count > 0:
        print(f"  识别失败: {failed_count} 张")
    
    if amounts:
        print(f"\n  金额明细:")
        print(f"  {'-'*76}")
        
        total = 0
        for i, (filename, amount) in enumerate(sorted(amounts), 1):
            print(f"  {i:2d}. {filename:43s} ¥{amount:8.2f}")
            total += amount
        
        print(f"\n  {'='*76}")
        print(f"  识别总计: ¥{total:.2f}")
        print(f"  预期金额: ¥{expected_amount:.2f}")
        diff = abs(total - expected_amount)
        print(f"  差额: ¥{diff:.2f}")
        
        if diff < 0.01:
            print("  ✓ 金额完美匹配！")
        elif diff < 50:
            print("  ⚠ 接近预期，可能有小额差异或个别图片识别有误")
        else:
            print("  ✗ 差异较大，建议人工核对")
            
        # 如果有差异，提供分析
        if diff > 0.01:
            if total < expected_amount:
                print(f"\n  提示: 当前少 ¥{expected_amount - total:.2f}，可能有图片未识别成功")
            else:
                print(f"\n  提示: 当前多 ¥{total - expected_amount:.2f}，可能有重复或识别错误")
        
        # 显示未识别的文件
        if failed_count > 0:
            print(f"\n  未识别的图片 ({failed_count}张):")
            print(f"  {'-'*76}")
            failed_names = [f.name for f in image_files if f.name not in [name for name, _ in amounts]]
            for name in failed_names:
                print(f"    - {name}")
        
        return total
    return 0

def main():
    # 获取当前目录
    current_dir = Path(__file__).parent
    
    # 定义要处理的文件夹及其预期金额
    folders = [
        ("对应2980微信支付记录", 2980.0),
        ("对应4700微信支付记录", 4700.0),
        ("对应6405微信支付记录", 6405.0),
    ]
    
    print("="*80)
    print(f"微信支付截图OCR识别工具 - 批量文件夹处理")
    print("="*80)
    
    all_results = []
    
    for folder_name, expected_amount in folders:
        folder_path = current_dir / folder_name
        
        print(f"\n{'='*80}")
        print(f"处理文件夹: {folder_name}")
        print(f"预期金额: ¥{expected_amount:.2f}")
        print(f"{'='*80}\n")
        
        if not folder_path.exists():
            print(f"  ✗ 文件夹不存在: {folder_path}")
            continue
        
        amounts, image_files = process_folder(folder_path, expected_amount)
        
        if amounts is not None:
            total = print_folder_summary(folder_name, amounts, image_files, expected_amount)
            all_results.append((folder_name, total, expected_amount))
    
    # 打印总体汇总
    if all_results:
        print(f"\n\n{'='*80}")
        print(f"总体汇总")
        print(f"{'='*80}\n")
        
        grand_total = 0
        grand_expected = 0
        
        for folder_name, total, expected in all_results:
            print(f"  {folder_name:40s} 识别: ¥{total:8.2f}  预期: ¥{expected:8.2f}  差额: ¥{abs(total-expected):8.2f}")
            grand_total += total
            grand_expected += expected
        
        print(f"\n  {'-'*78}")
        print(f"  {'所有文件夹合计':40s} 识别: ¥{grand_total:8.2f}  预期: ¥{grand_expected:8.2f}  差额: ¥{abs(grand_total-grand_expected):8.2f}")
        print(f"  {'='*78}")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()

