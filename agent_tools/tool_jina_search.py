import logging
import os
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.general_tools import get_config_value

logger = logging.getLogger(__name__)

from bs4 import BeautifulSoup
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.summarizers.text_rank import TextRankSummarizer
import nltk

class ContentCleaner:
    def __init__(self):
        # 增强的噪声模式
        self.noise_patterns = [
            # HTML标签噪音
            r'<script[^>]*>.*?</script>',
            r'<style[^>]*>.*?</style>',
            r'<!--.*?-->',
            r'<nav[^>]*>.*?</nav>',
            r'<header[^>]*>.*?</header>',
            r'<footer[^>]*>.*?</footer>',
            r'<aside[^>]*>.*?</aside>',
            r'<noscript[^>]*>.*?</noscript>',
            
            # 广告和推广相关
            r'class="[^"]*(ad|advertisement|banner|promo|sponsor|widget)[^"]*"',
            r'id="[^"]*(ad|advertisement|banner|promo|sponsor)[^"]*"',
            
            # 导航和菜单
            r'class="[^"]*(menu|navigation|breadcrumb|pagination|toolbar)[^"]*"',
            r'id="[^"]*(menu|navigation|breadcrumb|pagination)[^"]*"',
            
            # 侧边栏和无关内容
            r'class="[^"]*(sidebar|widget|related|comment|share)[^"]*"',
            r'id="[^"]*(sidebar|widget|related|comment)[^"]*"',
            
            # 技术噪音
            r'\[\d+\]\s*',  # 引用标记如 [1]
            r'\*\s*[A-Za-z]+\s*\*\s*\|\s*[A-Za-z]+\s*\|\s*[A-Za-z]+',  # 表格头部
            r'\|[-\s\|]+\|',  # 表格分隔线
        ]
        
        # 中文垃圾内容模式
        self.chinese_noise_patterns = [
            r'免责声明.*?(?:。|$)',
            r'本文不代表.*?(?:。|$)',
            r'转载请注明出处.*?(?:。|$)',
            r'编辑\s*[:：].*?(?:。|$)',
            r'作者\s*[:：].*?(?:。|$)',
            r'来源\s*[:：].*?(?:。|$)',
            r'关注微信公众号.*?(?:。|$)',
            r'扫码关注.*?(?:。|$)',
            r'点击查看详情.*?(?:。|$)',
            r'了解更多.*?(?:。|$)',
        ]
        
        # 英文垃圾内容模式
        self.english_noise_patterns = [
            r'Disclaimer.*?(?:\.|$)',
            r'This article does not represent.*?(?:\.|$)',
            r'Reprinted with permission.*?(?:\.|$)',
            r'Editor\s*[:].*?(?:\.|$)',
            r'Author\s*[:].*?(?:\.|$)',
            r'Source\s*[:].*?(?:\.|$)',
            r'Follow us on.*?(?:\.|$)',
            r'Scan to follow.*?(?:\.|$)',
        ]

    def clean_jina_content(self, content, content_type="auto"):
        """直接清洗Jina返回的内容"""
        if content_type == "auto":
            content_type = self.detect_content_type(content)

        if content_type == "html":
            return self._clean_html_content(content)
        elif content_type == "pdf":
            return self._clean_pdf_content(content)
        else:
            return self._clean_text_content(content)

    def detect_content_type(self, content):
        """自动检测内容类型"""
        if content.startswith('<!DOCTYPE') or content.startswith('<html'):
            return "html"
        elif "PDF" in content.upper() or "%PDF" in content:
            return "pdf"
        else:
            return "text"

    def _clean_html_content(self, html_content):
        """清洗HTML内容"""
        # Jina可能已经返回了Markdown，但进一步清理
        soup = BeautifulSoup(html_content, 'html.parser')

        # 移除不需要的元素
        for element in soup(['script', 'style', 'nav', 'header', 'footer']):
            element.decompose()

        # 提取文本并清理
        text = soup.get_text()
        text = self._post_process_text(text)
        return text

    def _clean_pdf_content(self, pdf_content):
        """清洗PDF内容"""
        # 移除PDF元数据行
        lines = pdf_content.split('\n')
        clean_lines = []

        for line in lines:
            line = line.strip()
            # 过滤掉页码、文件路径等噪声
            if (len(line) > 20 and
                not re.search(r'page\s+\d+', line.lower()) and
                not re.search(r'file:///', line) and
                not re.search(r'^\d+$', line)):
                clean_lines.append(line)

        return '\n'.join(clean_lines)

    def _clean_text_content(self, text_content):
        """清洗纯文本内容"""
        return self._post_process_text(text_content)

    def _post_process_text(self, text):
        """增强的文本后处理"""
        if not text or not text.strip():
            return ""
            
        # 移除过多的空格和换行
        text = re.sub(r'\s+', ' ', text)
        
        # 应用通用噪声模式
        for pattern in self.noise_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
        
        # 根据文本特征应用对应的语言模式
        if self._is_chinese_text(text):
            for pattern in self.chinese_noise_patterns:
                text = re.sub(pattern, '', text)
        else:
            for pattern in self.english_noise_patterns:
                text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # 移除URL但保留域名信息
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+(?!\S)', '', text)
        
        # 清理多余的标点符号
        text = re.sub(r'[\.!?]{3,}', '... ', text)  # 多个标点合并
        text = re.sub(r'\s+[\.!?]\s+', '. ', text)  # 句子间多余空格
        
        # 移除开头和结尾的无意义字符
        text = text.strip(' \t\n\r\xa0·•–—')
        
        return text
    
    def _is_chinese_text(self, text):
        """简单判断是否为中文文本"""
        if not text:
            return False
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        total_chars = len(re.findall(r'[\w\u4e00-\u9fff]', text))
        return chinese_chars / max(total_chars, 1) > 0.3  # 中文字符占比超过30%


class SmartSummarizer:
    def __init__(self):
        # 确保NLTK数据可用
        self._ensure_nltk_resources()
        
        self.summarizers = {
            'lsa': LsaSummarizer(),
            'text_rank': TextRankSummarizer()
        }
    
    def _ensure_nltk_resources(self):
        """确保NLTK所需资源都已下载"""
        required_resources = [
            'punkt',      # 基础分词模型
            'punkt_tab'   # 新版NLTK需要的tabular punkt数据
        ]
        
        for resource in required_resources:
            try:
                nltk.data.find(f'tokenizers/{resource}')
                logger.debug(f"✅ NLTK resource '{resource}' already available")
            except LookupError:
                logger.warning(f"🔄 Downloading NLTK resource: {resource}")
                try:
                    nltk.download(resource, quiet=True)
                    logger.info(f"✅ Successfully downloaded NLTK resource: {resource}")
                except Exception as e:
                    logger.error(f"❌ Failed to download NLTK resource '{resource}': {e}")
                    raise RuntimeError(f"NLTK resource '{resource}' is required but cannot be downloaded")

    def estimate_tokens(self, text):
        """估算token数量"""
        return int(len(text.split()) * 1.3)

    def adaptive_summary(self, text, target_tokens=None, quality_preset="balanced"):
        """增强的自适应摘要"""
        if not text or len(text.strip()) < 100:
            return text
            
        current_tokens = self.estimate_tokens(text)

        if target_tokens and current_tokens <= target_tokens:
            return text

        # 更精细的质量预设
        preset_configs = {
            "high": {"ratio": 0.4, "min_sentences": 8, "max_sentences": 20},
            "balanced": {"ratio": 0.3, "min_sentences": 5, "max_sentences": 15},
            "fast": {"ratio": 0.2, "min_sentences": 3, "max_sentences": 10},
            "ultra_fast": {"ratio": 0.15, "min_sentences": 2, "max_sentences": 8}
        }
        
        config = preset_configs.get(quality_preset, preset_configs["balanced"])
        
        # 分析文本特征
        sentences = nltk.sent_tokenize(text)
        avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences)
        
        # 根据文本特征动态调整
        if len(sentences) < 5:
            return text  # 太短无需摘要
        
        # 计算目标句子数
        target_sentences = max(
            config["min_sentences"], 
            min(config["max_sentences"], int(len(sentences) * config["ratio"]))
        )
        
        # 智能选择摘要方法
        method = self._select_best_method(sentences, avg_sentence_length)
        
        # 执行摘要
        summary = self.extractive_summary(text, target_sentences, method)
        
        # 后处理：确保摘要质量和连贯性
        summary = self._post_process_summary(summary, sentences)
        
        return summary
    
    def _select_best_method(self, sentences, avg_length):
        """根据文本特征选择最佳摘要方法"""
        sentence_count = len(sentences)
        total_words = sum(len(s.split()) for s in sentences)
        
        # TextRank适合长文档和复杂结构
        if sentence_count > 30 or avg_length > 25:
            return 'text_rank'
        # LSA适合中等长度文档
        elif sentence_count > 10:
            return 'lsa'
        # 简单截取适合短文档
        else:
            return 'simple'
    
    def _post_process_summary(self, summary, original_sentences):
        """摘要后处理，提升可读性和连贯性"""
        if not summary:
            return ""
            
        # 确保摘要以完整句子结束
        sentences = nltk.sent_tokenize(summary)
        if sentences:
            # 如果最后一个句子不完整，移除它
            last_sentence = sentences[-1]
            if not (last_sentence.endswith('.') or last_sentence.endswith('!') or last_sentence.endswith('?')):
                sentences = sentences[:-1]
            
            # 确保摘要不过短
            if len(' '.join(sentences)) < 100 and len(original_sentences) > 3:
                # 返回前几个完整句子
                safe_count = min(3, len(original_sentences))
                return ' '.join(original_sentences[:safe_count])
            
            return ' '.join(sentences)
        
        return summary

    def extractive_summary(self, text, sentences_count=5, method='lsa'):
        """增强的提取式摘要，支持多种方法"""
        if len(text.split()) < 300:
            return text  # 短内容无需摘要

        sentences = nltk.sent_tokenize(text)
        if len(sentences) <= sentences_count:
            return text  # 句子数不够摘要
        
        # 简单截取模式
        if method == 'simple':
            return " ".join(sentences[:sentences_count])
        
        # 使用sumy库进行智能摘要
        try:
            # 自动检测语言
            language = "chinese" if self._is_chinese_text(text) else "english"
            parser = PlaintextParser.from_string(text, Tokenizer(language))
            summarizer = self.summarizers.get(method, self.summarizers['lsa'])
            
            summary_sentences = summarizer(parser.document, sentences_count)
            return " ".join(str(sentence) for sentence in summary_sentences)
        except Exception as e:
            logger.warning(f"智能摘要失败，回退到简单截取: {e}")
            return " ".join(sentences[:sentences_count])

class ContentQualityController:
    def __init__(self):
        self.min_content_length = 100
        self.max_similarity_threshold = 0.8
        
    def assess_content_quality(self, content, metadata):
        """评估内容质量并返回评分"""
        score = 100
        issues = []
        
        # 长度检查
        if len(content) < self.min_content_length:
            score -= 30
            issues.append("内容过短")
        
        # 空内容检查
        if not content or not content.strip():
            score = 0
            issues.append("内容为空")
            return {"score": 0, "issues": issues, "quality": "poor"}
        
        # 重复字符检查
        if self._has_excessive_repetition(content):
            score -= 20
            issues.append("存在大量重复内容")
        
        # 噪声比例检查
        noise_ratio = self._calculate_noise_ratio(content)
        if noise_ratio > 0.3:
            score -= 25
            issues.append(f"噪声内容比例过高 ({noise_ratio:.1%})")
        
        # 信息密度检查
        info_density = self._calculate_info_density(content)
        if info_density < 0.1:
            score -= 15
            issues.append("信息密度过低")
        
        # 确定质量等级
        if score >= 80:
            quality = "excellent"
        elif score >= 60:
            quality = "good"
        elif score >= 40:
            quality = "fair"
        else:
            quality = "poor"
            
        return {
            "score": max(0, score),
            "issues": issues,
            "quality": quality,
            "metrics": {
                "length": len(content),
                "noise_ratio": noise_ratio,
                "info_density": info_density
            }
        }
    
    def deduplicate_contents(self, contents):
        """内容去重"""
        if len(contents) <= 1:
            return contents
            
        unique_contents = []
        seen_hashes = set()
        
        for content in contents:
            # 计算内容哈希
            content_hash = hash(content["content"][:200])  # 取前200字符计算hash
            
            if content_hash not in seen_hashes:
                unique_contents.append(content)
                seen_hashes.add(content_hash)
            else:
                logger.debug(f"发现重复内容，URL: {content.get('url', 'unknown')}")
                
        return unique_contents
    
    def sort_by_quality_and_relevance(self, contents, query):
        """根据质量和相关性排序内容"""
        scored_contents = []
        
        for content in contents:
            quality_score = content.get("quality_score", {}).get("score", 50)
            relevance_score = self._calculate_relevance_score(content, query)
            
            # 综合评分 = 质量分数 * 0.7 + 相关性分数 * 0.3
            composite_score = quality_score * 0.7 + relevance_score * 0.3
            
            content["composite_score"] = composite_score
            scored_contents.append(content)
        
        # 按综合评分降序排列
        return sorted(scored_contents, key=lambda x: x["composite_score"], reverse=True)
    
    def _has_excessive_repetition(self, text):
        """检查是否存在过度重复"""
        if len(text) < 50:
            return False
            
        # 检查连续重复字符
        for i in range(len(text) - 10):
            substring = text[i:i+10]
            if text.count(substring) > 3:
                return True
        return False
    
    def _calculate_noise_ratio(self, text):
        """计算噪声内容比例"""
        if not text:
            return 1.0
            
        noise_indicators = [
            r'广告', r'推广', r'点击', r'详情', r'关注',
            r'Advertisement', r'Click', r'Details', r'Follow',
            r'\[.{0,10}\]',  # 方括号内容
            r'\*.{0,20}\*',  # 星号包围内容
        ]
        
        noise_matches = 0
        total_chars = len(text)
        
        for pattern in noise_indicators:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            noise_matches += matches * 10  # 每个匹配计10个字符
            
        return min(noise_matches / max(total_chars, 1), 1.0)
    
    def _calculate_info_density(self, text):
        """计算信息密度"""
        if not text:
            return 0.0
            
        # 简单的信息密度计算：有效词汇比例
        words = re.findall(r'\w+', text)
        if not words:
            return 0.0
            
        # 过滤停用词和无意义词汇
        meaningful_words = [w for w in words if len(w) > 2]
        return len(meaningful_words) / len(words)
    
    def _calculate_relevance_score(self, content, query):
        """计算查询相关性得分"""
        if not query or not content:
            return 50
            
        # 简单的相关性计算
        text_fields = [
            content.get("title", ""),
            content.get("description", ""),
            content.get("content", "")[:500]  # 只取前500字符
        ]
        
        combined_text = " ".join(text_fields).lower()
        query_lower = query.lower()
        
        # 计算查询词在文本中的出现频率
        query_words = query_lower.split()
        matches = sum(1 for word in query_words if word in combined_text)
        relevance = (matches / len(query_words)) * 100 if query_words else 50
        
        return min(relevance, 100)

class SimplifiedJinaProcessor:
    def __init__(self):
        self.cleaner = ContentCleaner()
        self.summarizer = SmartSummarizer()
        self.quality_controller = ContentQualityController()
        self.processed_cache = {}
        
        # 处理统计
        self.stats = {
            "processed_count": 0,
            "failed_count": 0,
            "quality_distribution": {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
        }

    def process_retrieved_content(self, jina_results, max_total_tokens=120000):
        """增强的内容处理，包含质量控制"""
        processed_results = []
        current_total_tokens = 0

        content = jina_results.get('content', '')
        url = jina_results.get('url', 'unknown')
        title = jina_results.get('title', '')
        description = jina_results.get('description', '')
        publish_time = jina_results.get('publish_time', 'unknown')

        # 更新统计
        self.stats["processed_count"] += 1
        
        # 内容质量评估
        metadata = {
            "url": url,
            "title": title,
            "description": description,
            "publish_time": publish_time
        }
        
        quality_assessment = self.quality_controller.assess_content_quality(content, metadata)
        
        # 如果质量很差，跳过该内容
        if quality_assessment["quality"] == "poor":
            self.stats["failed_count"] += 1
            self.stats["quality_distribution"]["poor"] += 1
            logger.warning(f"跳过低质量内容: {url}, 问题: {quality_assessment['issues']}
")
            return {
                "processed_results": [],
                "total_tokens": 0,
                "within_limit": True,
                "skipped_reason": quality_assessment["issues"]
            }
        
        # 更新质量分布统计
        self.stats["quality_distribution"][quality_assessment["quality"]] += 1

        # 内容清洗
        cleaned_content = self.cleaner.clean_jina_content(content)

        # 估算token并决定是否压缩
        token_count = self.summarizer.estimate_tokens(cleaned_content)

        if token_count > 3000:  # 确保有足够内容进行摘要
            compressed_content = self.summarizer.adaptive_summary(
                cleaned_content,
                target_tokens=3000,
                quality_preset="balanced"
            )
            token_count = self.summarizer.estimate_tokens(compressed_content)
            cleaned_content = compressed_content

        result_data = {
            "success": True,
            "content": cleaned_content,
            "token_count": token_count,
            "quality_score": quality_assessment,
            "metadata": {
                "url": url,
                "title": title,
                "description": description,
                "publish_time": publish_time,
                "cleaned": True,
                "compressed": token_count < self.summarizer.estimate_tokens(cleaned_content),
                "original_length": len(content),
                "cleaned_length": len(cleaned_content)
            }
        }

        processed_results.append(result_data)
        current_total_tokens += token_count

        return {
            "processed_results": processed_results,
            "total_tokens": current_total_tokens,
            "within_limit": current_total_tokens <= max_total_tokens,
            "quality_stats": self.stats
        }

    def build_analysis_context(self, processed_results):
        """构建分析上下文"""
        context_parts = []

        for i, result in enumerate(processed_results, 1):
            context_parts.append(f"【来源 {i} - {result['metadata']['url']}】")

            if result['metadata']['compressed']:
                context_parts.append(
                    f"*(内容已从 {result['metadata']['original_length']} 字符压缩至 {result['metadata']['cleaned_length']} 字符)*"
                )

            context_parts.append(result['content'])
            context_parts.append("---")

        return "\n".join(context_parts)

def parse_date_to_standard(date_str: str) -> str:
    """
    Convert various date formats to standard format (YYYY-MM-DD HH:MM:SS)

    Args:
        date_str: Date string in various formats, such as "2025-10-01T08:19:28+00:00", "4 hours ago", "1 day ago", "May 31, 2025"

    Returns:
        Standard format datetime string, such as "2025-10-01 08:19:28"
    """
    if not date_str or date_str == "unknown":
        return "unknown"

    # Handle relative time formats
    if "ago" in date_str.lower():
        try:
            now = datetime.now()
            if "hour" in date_str.lower():
                hours = int(re.findall(r"\d+", date_str)[0])
                target_date = now - timedelta(hours=hours)
            elif "day" in date_str.lower():
                days = int(re.findall(r"\d+", date_str)[0])
                target_date = now - timedelta(days=days)
            elif "week" in date_str.lower():
                weeks = int(re.findall(r"\d+", date_str)[0])
                target_date = now - timedelta(weeks=weeks)
            elif "month" in date_str.lower():
                months = int(re.findall(r"\d+", date_str)[0])
                target_date = now - timedelta(days=months * 30)  # Approximate handling
            else:
                return "unknown"
            return target_date.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    # Handle ISO 8601 format, such as "2025-10-01T08:19:28+00:00"
    try:
        if "T" in date_str and ("+" in date_str or "Z" in date_str or date_str.endswith("00:00")):
            # Remove timezone information, keep only date and time part
            if "+" in date_str:
                date_part = date_str.split("+")[0]
            elif "Z" in date_str:
                date_part = date_str.replace("Z", "")
            else:
                date_part = date_str

            # Parse ISO format
            if "." in date_part:
                # Handle microseconds part, such as "2025-10-01T08:19:28.123456"
                parsed_date = datetime.strptime(date_part.split(".")[0], "%Y-%m-%dT%H:%M:%S")
            else:
                # Standard ISO format "2025-10-01T08:19:28"
                parsed_date = datetime.strptime(date_part, "%Y-%m-%dT%H:%M:%S")
            return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # Handle other common formats
    try:
        # Handle "May 31, 2025" format
        if "," in date_str and len(date_str.split()) >= 3:
            parsed_date = datetime.strptime(date_str, "%b %d, %Y")
            return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    try:
        # Handle "2025-10-01" format
        if re.match(r"\d{4}-\d{2}-\d{2}$", date_str):
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
            return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # If unable to parse, return original string
    return date_str


class WebScrapingJinaTool:
    def __init__(self):
        self.api_key = os.environ.get("JINA_API_KEY")
        if not self.api_key:
            raise ValueError("Jina API key not provided! Please set JINA_API_KEY environment variable.")
        
        # 缓存设置
        self.cache = {}
        self.cache_ttl = 3600  # 1小时缓存时间
        self.max_cache_size = 100
        
        # 性能统计
        self.stats = {
            "requests_made": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0
        }

    def __call__(self, query: str) -> List[Dict[str, Any]]:
        print(f"Searching for {query}")
        all_urls = self._jina_search(query)
        return_content = []
        print(f"Found {len(all_urls)} URLs")
        if len(all_urls) > 3:
            # Randomly select three to form new all_urls
            all_urls = random.sample(all_urls, 3)
        for url in all_urls:
            # 检查缓存
            cached_result = self._get_from_cache(url)
            if cached_result:
                print(f"Cache hit for {url}")
                self.stats["cache_hits"] += 1
                return_content.append(cached_result)
                continue
            
            #print(f"Scraping {url}")
            scraped_content = self._jina_scrape(url)
            
            # 如果成功获取内容，加入缓存
            if scraped_content.get("content") and not scraped_content.get("error"):
                self._add_to_cache(url, scraped_content)
                print(f"Scraped and cached {url}")
            else:
                self.stats["errors"] += 1
                print(f"Failed to scrape {url}: {scraped_content.get('error', 'Unknown error')}")
                
            return_content.append(scraped_content)
            self.stats["requests_made"] += 1

        return return_content
    
    def _get_from_cache(self, url):
        """从缓存获取内容"""
        cache_key = self._generate_cache_key(url)
        if cache_key in self.cache:
            cached_item = self.cache[cache_key]
            # 检查是否过期
            if time.time() - cached_item["timestamp"] < self.cache_ttl:
                return cached_item["data"]
            else:
                # 删除过期缓存
                del self.cache[cache_key]
        return None
    
    def _add_to_cache(self, url, data):
        """添加内容到缓存"""
        # 如果缓存满了，删除最旧的条目
        if len(self.cache) >= self.max_cache_size:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]["timestamp"])
            del self.cache[oldest_key]
        
        cache_key = self._generate_cache_key(url)
        self.cache[cache_key] = {
            "data": data,
            "timestamp": time.time()
        }
    
    def _generate_cache_key(self, url):
        """生成缓存键"""
        # 使用URL的哈希值作为缓存键
        return str(hash(url))
    
    def get_stats(self):
        """获取工具统计信息"""
        total_requests = self.stats["requests_made"] + self.stats["cache_hits"]
        cache_hit_rate = (self.stats["cache_hits"] / max(total_requests, 1)) * 100
        
        return {
            "total_requests": total_requests,
            "cache_hits": self.stats["cache_hits"],
            "cache_misses": self.stats["requests_made"],
            "cache_hit_rate": f"{cache_hit_rate:.1f}%",
            "errors": self.stats["errors"],
            "current_cache_size": len(self.cache)
        }

    def _jina_scrape(self, url: str) -> Dict[str, Any]:
        """带重试机制的Jina内容抓取"""
        max_retries = 3
        base_delay = 1  # 基础延迟秒数
        
        for attempt in range(max_retries):
            try:
                jina_url = f"https://r.jina.ai/{url}"
                headers = {
                    "Accept": "application/json",
                    "Authorization": self.api_key,
                    "X-Timeout": "15",  # 增加超时时间
                    "X-With-Generated-Alt": "true",
                    "User-Agent": "Mozilla/5.0 (compatible; AI-News-Bot/1.0)",
                }
                
                # 使用会话保持连接
                session = requests.Session()
                session.headers.update(headers)
                
                response = session.get(
                    jina_url, 
                    timeout=(5, 20)  # (连接超时, 读取超时)
                )
                
                # 处理不同的HTTP状态码
                if response.status_code == 200:
                    response_dict = response.json()
                    return {
                        "url": response_dict["data"]["url"],
                        "title": response_dict["data"]["title"],
                        "description": response_dict["data"]["description"],
                        "content": response_dict["data"]["content"],
                        "publish_time": response_dict["data"].get("publishedTime", "unknown"),
                        "attempts": attempt + 1
                    }
                elif response.status_code in [503, 524, 502, 504]:
                    # 服务器临时错误，可以重试
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(f"🔄 Jina API returned {response.status_code} for {url}, retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        continue
                    else:
                        raise Exception(f"Jina API持续返回错误状态码 {response.status_code}，已达到最大重试次数")
                else:
                    # 其他错误状态码
                    raise Exception(f"Jina API返回意外状态码 {response.status_code} for {url}")
                    
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"⏰ Jina API请求超时，重试中... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"❌ Jina API请求多次超时，放弃重试: {url}")
                    return {"url": url, "content": "", "error": "Request timeout after retries"}
                    
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"🔌 Jina API连接错误，重试中... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"❌ Jina API连接失败: {str(e)}")
                    return {"url": url, "content": "", "error": f"Connection failed: {str(e)}"}
                    
            except Exception as e:
                logger.error(f"❌ Jina API请求失败: {str(e)}")
                return {"url": url, "content": "", "error": str(e)}
        
        # 如果所有重试都失败
        return {"url": url, "content": "", "error": "All retry attempts failed"}

    def _jina_search(self, query: str) -> List[str]:
        url = f"https://s.jina.ai/?q={query}&n=1"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "X-Respond-With": "no-content",
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # 检查HTTP状态码

            json_data = response.json()

            # Check if response data is valid
            if json_data is None:
                print(f"⚠️ Jina API returned empty data, query: {query}")
                return []

            if "data" not in json_data:
                print(f"⚠️ Jina API response format abnormal, query: {query}, response: {json_data}")
                return []

            all_urls = []
            filtered_urls = []

            # Process search results, filter out content from TODAY_DATE and later
            for item in json_data.get("data", []):
                if "url" not in item:
                    continue

                # Get publication date and convert to standard format
                raw_date = item.get("date", "unknown")
                standardized_date = parse_date_to_standard(raw_date)

                # If unable to parse date, keep this result
                if standardized_date == "unknown" or standardized_date == raw_date:
                    filtered_urls.append(item["url"])
                    continue

                # Check if before TODAY_DATE
                today_date = get_config_value("TODAY_DATE")
                if today_date:
                    if today_date > standardized_date:
                        filtered_urls.append(item["url"])
                else:
                    # If TODAY_DATE is not set, keep all results
                    filtered_urls.append(item["url"])

            print(f"Found {len(filtered_urls)} URLs after filtering")
            return filtered_urls

        except requests.exceptions.RequestException as e:
            print(f"❌ Jina API request failed: {e}")
            return []
        except ValueError as e:
            print(f"❌ Jina API response parsing failed: {e}")
            return []
        except Exception as e:
            print(f"❌ Jina search unknown error: {e}")
            return []


mcp = FastMCP("Search")


@mcp.tool()
def get_information(query: str) -> str:
    """
    Use search tool to scrape and return main content information related to specified query in a structured way.

    Args:
        query: Key information or search terms you want to retrieve, will search for the most matching results on the internet.

    Returns:
        A string containing several retrieved web page contents, structured content includes:
        - URL: Original web page link
        - Title: Web page title
        - Description: Brief description of the web page
        - Publish Time: Content publication date (if available)
        - Content: Main text content of the web page (first 1000 characters)

        If scraping fails, returns corresponding error information.
    """
    try:
        print(datetime.now())
        tool = WebScrapingJinaTool()
        results = tool(query)
        processor = SimplifiedJinaProcessor()

        # Check if results are empty
        if not results:
            return f"⚠️ Search query '{query}' found no results. May be network issue or API limitation."

        # Process results with quality control
        all_processed_results = []
        total_tokens = 0
        
        for result in results:
            if "error" in result:
                all_processed_results.append({
                    "url": result.get("url", "unknown"),
                    "error": result['error'],
                    "content": ""
                })
            else:
                processed_batch = processor.process_retrieved_content(result)
                if processed_batch.get("processed_results"):
                    processed_result = processed_batch["processed_results"][0]
                    all_processed_results.append({
                        "url": result['url'],
                        "title": result['title'],
                        "description": result['description'],
                        "publish_time": result['publish_time'],
                        "content": processed_result["content"],
                        "tokens": processed_result["token_count"],
                        "quality": processed_result.get("quality_score", {}).get("quality", "unknown")
                    })
                    total_tokens += processed_result["token_count"]

        if not all_processed_results:
            return f"⚠️ Search query '{query}' returned no valid content after processing."
        
        # Build formatted output
        formatted_results = []
        for i, result in enumerate(all_processed_results, 1):
            if result.get("error"):
                formatted_results.append(f"❌ 来源 {i} 错误: {result['error']} (URL: {result['url']})")
            else:
                formatted_results.extend([
                    f"【来源 {i}】",
                    f"URL: {result['url']}",
                    f"标题: {result['title']}",
                    f"描述: {result['description']}",
                    f"发布时间: {result['publish_time']}",
                    f"内容质量: {result['quality'].upper()}",
                    f"Token数: {result['tokens']}",
                    "---",
                    f"{result['content'][:1000]}...",
                    "=" * 50
                ])
        
        # 添加工具统计信息
        tool_stats = tool.get_stats()
        processor_stats = processor.stats
        
        stats_info = [
            "\n📊 处理统计:",
            f"- 总请求数: {tool_stats['total_requests']}",
            f"- 缓存命中率: {tool_stats['cache_hit_rate']}",
            f"- 处理成功数: {processor_stats['processed_count'] - processor_stats['failed_count']}",
            f"- 质量分布: 优秀({processor_stats['quality_distribution']['excellent']}) "
                       f"良好({processor_stats['quality_distribution']['good']}) "
                       f"一般({processor_stats['quality_distribution']['fair']}) "
                       f"差({processor_stats['quality_distribution']['poor']})"
        ]
        
        formatted_results.extend(stats_info)
        

        # log_file = get_config_value("LOG_FILE")     
        # signature = get_config_value("SIGNATURE")
        # log_entry = {
        #     "signature": signature,
        #     "new_messages": [{"role": "tool:jinasearch", "content": "\n".join(formatted_results)}]
        # }
        # with open(log_file, "a", encoding="utf-8") as f:
        #     f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        return "\n".join(formatted_results)

    except Exception as e:
        return f"❌ Search tool execution failed: {str(e)}"

if __name__ == "__main__":
    # Run with streamable-http, support configuring host and port through environment variables to avoid conflicts
    port = int(os.getenv("SEARCH_HTTP_PORT", "8001"))
    mcp.run(transport="streamable-http", port=port)
