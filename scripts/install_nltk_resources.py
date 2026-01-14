#!/usr/bin/env python3
"""
NLTK 资源预安装脚本
用于在项目启动前确保所有必需的NLTK资源都已正确安装
"""

import os
import sys
import nltk
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_nltk_data_directories():
    """设置NLTK数据目录"""
    # 定义可能的数据目录
    data_dirs = [
        '/home/ec2-user/nltk_data',
        '/usr/local/share/nltk_data',
        '/usr/share/nltk_data',
        os.path.expanduser('~/.nltk_data'),
        os.path.join(os.getcwd(), 'nltk_data')
    ]
    
    # 创建必要的目录并添加到NLTK路径
    for data_dir in data_dirs:
        try:
            Path(data_dir).mkdir(parents=True, exist_ok=True)
            if data_dir not in nltk.data.path:
                nltk.data.path.append(data_dir)
            logger.info(f"✅ 确保NLTK目录可用: {data_dir}")
        except Exception as e:
            logger.warning(f"⚠️ 无法创建目录 {data_dir}: {e}")

def download_nltk_resources():
    """下载必需的NLTK资源"""
    required_resources = [
        'punkt',      # 基础分词模型
        'punkt_tab'   # 新版NLTK需要的tabular punkt数据
    ]
    
    success_count = 0
    
    for resource in required_resources:
        try:
            # 检查资源是否已存在
            nltk.data.find(f'tokenizers/{resource}')
            logger.info(f"✅ 资源已存在: {resource}")
            success_count += 1
            continue
        except LookupError:
            logger.info(f"🔄 下载资源: {resource}")
        
        # 尝试多种下载方法
        download_methods = [
            # 方法1: 默认下载
            lambda: nltk.download(resource, quiet=False),
            # 方法2: 指定临时目录下载
            lambda: nltk.download(resource, download_dir='/tmp/nltk_data', quiet=False),
        ]
        
        downloaded = False
        for i, method in enumerate(download_methods, 1):
            try:
                method()
                # 验证下载是否成功
                nltk.data.find(f'tokenizers/{resource}')
                logger.info(f"✅ 成功下载 {resource} (方法 {i})")
                success_count += 1
                downloaded = True
                break
            except Exception as e:
                logger.warning(f"⚠️ 方法 {i} 失败: {e}")
                continue
        
        if not downloaded:
            logger.error(f"❌ 无法下载资源: {resource}")
    
    return success_count == len(required_resources)

def test_nltk_functionality():
    """测试NLTK功能是否正常工作"""
    try:
        # 测试句子分割
        test_text = "这是第一句话。这是第二句话！这是第三句话？"
        sentences = nltk.sent_tokenize(test_text)
        logger.info(f"✅ 句子分割测试成功: {sentences}")
        
        # 测试英文句子分割
        english_text = "This is the first sentence. This is the second sentence!"
        eng_sentences = nltk.sent_tokenize(english_text)
        logger.info(f"✅ 英文句子分割测试成功: {eng_sentences}")
        
        return True
    except Exception as e:
        logger.error(f"❌ NLTK功能测试失败: {e}")
        return False

def main():
    """主函数"""
    logger.info("🚀 开始NLTK资源安装和验证...")
    
    # 设置数据目录
    setup_nltk_data_directories()
    
    # 下载资源
    if not download_nltk_resources():
        logger.error("❌ 资源下载失败，请检查网络连接")
        sys.exit(1)
    
    # 测试功能
    if not test_nltk_functionality():
        logger.error("❌ 功能测试失败")
        sys.exit(1)
    
    logger.info("🎉 NLTK资源安装和验证完成！")
    logger.info(f"NLTK数据路径: {nltk.data.path}")

if __name__ == "__main__":
    main()