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
        self.noise_patterns = [
            r'<script[^>]*>.*?</script>',
            r'<style[^>]*>.*?</style>',
            r'<!--.*?-->',
            r'<nav[^>]*>.*?</nav>',
            r'<header[^>]*>.*?</header>',
            r'<footer[^>]*>.*?</footer>',
            r'class="[^"]*(ad|banner|sidebar|menu|navigation)[^"]*"',
            r'id="[^"]*(ad|banner|sidebar|menu|navigation)[^"]*"'
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
        """文本后处理"""
        # 移除过多的空格
        text = re.sub(r'\s+', ' ', text)

        # 移除URL（保留链接文本）
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)

        return text.strip()


class SmartSummarizer:
    def __init__(self):
        # 确保NLTK数据可用
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt')

        self.summarizers = {
            'lsa': LsaSummarizer(),
            'text_rank': TextRankSummarizer()
        }

    def estimate_tokens(self, text):
        """估算token数量"""
        return int(len(text.split()) * 1.3)

    def adaptive_summary(self, text, target_tokens=None, quality_preset="balanced"):
        """自适应摘要"""
        current_tokens = self.estimate_tokens(text)

        if target_tokens and current_tokens <= target_tokens:
            return text

        # 根据质量预设调整参数
        if quality_preset == "high":
            sentences_ratio = 0.4
            min_sentences = 8
        elif quality_preset == "balanced":
            sentences_ratio = 0.3
            min_sentences = 5
        else:  # fast
            sentences_ratio = 0.2
            min_sentences = 3

        # 计算目标句子数
        sentences = nltk.sent_tokenize(text)
        target_sentences = max(min_sentences, int(len(sentences) * sentences_ratio))

        # 选择摘要方法
        if len(sentences) > 50:
            method = 'text_rank'  # 长文档用TextRank
        else:
            method = 'lsa'        # 短文档用LSA

        summary = self.extractive_summary(text, target_sentences, method)

        return summary

    def extractive_summary(self, text, sentences_count=5, method='lsa'):
        """提取式摘要"""
        if len(text.split()) < 300:
            return text  # 短内容无需摘要

        parser = PlaintextParser.from_string(text, Tokenizer("chinese"))
        summarizer = self.summarizers.get(method, self.summarizers['lsa'])

        summary_sentences = summarizer(parser.document, sentences_count)
        return " ".join(str(sentence) for sentence in summary_sentences)

class SimplifiedJinaProcessor:
    def __init__(self):
        self.cleaner = ContentCleaner()
        self.summarizer = SmartSummarizer()
        self.processed_cache = {}

    def process_retrieved_content(self, jina_results, max_total_tokens=120000):
        """直接处理Jina返回的内容"""
        processed_results = []
        current_total_tokens = 0

        content = jina_results.get('content', '')
        #content = result['content']
        url = jina_results.get('url', 'unknown')
        #url = result['url']

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
            "metadata": {
                "url": url,
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
            "within_limit": current_total_tokens <= max_total_tokens
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

    def __call__(self, query: str) -> List[Dict[str, Any]]:
        print(f"Searching for {query}")
        all_urls = self._jina_search(query)
        return_content = []
        print(f"Found {len(all_urls)} URLs")
        if len(all_urls) > 1:
            # Randomly select three to form new all_urls
            all_urls = random.sample(all_urls, 1)
        for url in all_urls:
            print(f"Scraping {url}")
            return_content.append(self._jina_scrape(url))
            print(f"Scraped {url}")

        return return_content

    def _jina_scrape(self, url: str) -> Dict[str, Any]:
        try:
            jina_url = f"https://r.jina.ai/{url}"
            headers = {
                "Accept": "application/json",
                "Authorization": self.api_key,
                "X-Timeout": "10",
                "X-With-Generated-Alt": "true",
            }
            response = requests.get(jina_url, headers=headers)

            if response.status_code != 200:
                raise Exception(f"Jina AI Reader Failed for {url}: {response.status_code}")

            response_dict = response.json()

            return {
                "url": response_dict["data"]["url"],
                "title": response_dict["data"]["title"],
                "description": response_dict["data"]["description"],
                "content": response_dict["data"]["content"],
                "publish_time": response_dict["data"].get("publishedTime", "unknown"),
            }

        except Exception as e:
            logger.error(str(e))
            return {"url": url, "content": "", "error": str(e)}

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

        # Convert results to string format
        formatted_results = []
        for result in results:
            if "error" in result:
                formatted_results.append(f"Error: {result['error']}")
            else:
                processed_batch = processor.process_retrieved_content(result)
                formatted_results.append(
                    f"""
URL: {result['url']}
Title: {result['title']}
Description: {result['description']}
Publish Time: {result['publish_time']}
Content: {processed_batch['processed_results']}
Tokens: {processed_batch['total_tokens']}
"""
                )

        if not formatted_results:
            return f"⚠️ Search query '{query}' returned empty results."
        

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
