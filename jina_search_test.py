#!/usr/bin/env python3
"""
Jina Search工具全面性能测试脚本
直接调用tool_jina_search进行新闻检索和信息过滤测试
重点监控性能指标、成功率、内容质量和缓存效果
支持多种测试模式和详细的性能分析
"""

import os
import sys
import time
import json
from datetime import datetime
from typing import List, Dict, Any

# 添加项目路径
sys.path.append('/home/ec2-user/AI-Trader')

# 加载环境变量
def load_env_vars():
    """加载环境变量"""
    from dotenv import load_dotenv
    
    # 使用python-dotenv加载环境变量
    env_loaded = load_dotenv('/home/ec2-user/AI-Trader/.env')
    
    if env_loaded:
        print("✅ 环境变量加载完成")
        # 验证关键变量
        jina_key = os.environ.get("JINA_API_KEY")
        if jina_key:
            print(f"🔑 JINA_API_KEY已设置 (长度: {len(jina_key)})")
        else:
            print("⚠️  JINA_API_KEY未在.env文件中找到")
    else:
        print("⚠️  .env文件不存在或加载失败，使用系统环境变量")
        
    # 如果.env加载失败，尝试手动解析
    env_file = '/home/ec2-user/AI-Trader/.env'
    if not env_loaded and os.path.exists(env_file):
        print("🔄 尝试手动解析.env文件...")
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip().strip('"')
            print("✅ 手动加载环境变量完成")
        except Exception as e:
            print(f"❌ 手动加载失败: {e}")

def test_jina_search_tool(keywords: List[str] = None, concurrent: bool = False, detailed: bool = True):
    """测试Jina Search工具性能
    
    Args:
        keywords: 测试关键词列表
        concurrent: 是否启用并发测试（暂未实现）
        detailed: 是否显示详细信息
    """
    
    # 加载环境变量
    load_env_vars()
    
    # 默认测试关键词
    if keywords is None:
        keywords = ["半导体", "新能源", "人工智能"]
    
    print(f"🚀 开始Jina Search工具性能测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试关键词: {', '.join(keywords)}")
    print(f"测试模式: {'详细' if detailed else '简洁'}")
    print(f"⏱️  时间限制: 60秒")
    print("=" * 60)
    
    # 检查必要配置
    jina_api_key = os.environ.get("JINA_API_KEY")
    if not jina_api_key:
        print("❌ 错误: JINA_API_KEY环境变量未设置")
        print("💡 请在.env文件中设置JINA_API_KEY")
        return None
    
    try:
        # 导入Jina搜索工具
        from agent_tools.tool_jina_search import WebScrapingJinaTool, SimplifiedJinaProcessor
        
        # 初始化搜索工具
        search_tool = WebScrapingJinaTool()
        processor = SimplifiedJinaProcessor()
        
        total_start_time = time.time()
        all_results = []
        performance_stats = {
            'total_time': 0,
            'keyword_times': [],
            'successful_requests': 0,
            'failed_requests': 0,
            'total_tokens': 0,
            'quality_stats': {'excellent': 0, 'good': 0, 'fair': 0, 'poor': 0}
        }
        
        # 顺序执行测试
        for i, keyword in enumerate(keywords, 1):
            print(f"\n🔍 第 {i}/{len(keywords)} 个关键词: '{keyword}'")
            print("-" * 50)
            
            keyword_start_time = time.time()
            
            try:
                # 执行搜索
                if detailed:
                    print(f"📡 正在搜索: '{keyword}'...")
                
                raw_results = search_tool(keyword)
                search_time = time.time() - keyword_start_time
                
                if detailed:
                    print(f"✅ 搜索完成 (耗时: {search_time:.2f}秒)")
                    print(f"   获取到 {len(raw_results)} 个原始结果")
                else:
                    print(f"✅ '{keyword}' 搜索完成 ({len(raw_results)}结果, {search_time:.1f}s)")
                
                # 处理内容质量
                processed_results = []
                keyword_tokens = 0
                successful_count = 0
                filtered_count = 0
                
                for j, raw_result in enumerate(raw_results, 1):
                    if detailed:
                        print(f"\n--- 处理结果 {j}/{len(raw_results)} ---")
                    
                    if "error" in raw_result:
                        if detailed:
                            print(f"❌ 错误: {raw_result['error']}")
                            print(f"URL: {raw_result.get('url', 'unknown')}")
                        performance_stats['failed_requests'] += 1
                        continue
                    
                    # 处理内容
                    try:
                        processed_batch = processor.process_retrieved_content(raw_result)
                        
                        if processed_batch.get("processed_results"):
                            processed_result = processed_batch["processed_results"][0]
                            
                            if detailed:
                                print(f"✅ 内容处理成功")
                                print(f"URL: {raw_result.get('url', 'unknown')}")
                                print(f"标题: {raw_result.get('title', '无标题')}")
                                print(f"质量评分: {processed_result.get('quality_score', {}).get('score', 'N/A')}/100")
                                print(f"质量等级: {processed_result.get('quality_score', {}).get('quality', 'unknown').upper()}")
                                print(f"Token数: {processed_result.get('token_count', 0)}")
                                print(f"内容长度: {len(processed_result.get('content', ''))} 字符")
                                
                                content_preview = processed_result.get('content', '')[:100]
                                print(f"内容预览: {content_preview}{'...' if len(processed_result.get('content', '')) > 100 else ''}")
                            
                            # 更新统计
                            successful_count += 1
                            keyword_tokens += processed_result.get('token_count', 0)
                            quality = processed_result.get('quality_score', {}).get('quality', 'unknown')
                            performance_stats['quality_stats'][quality] += 1
                            
                            processed_results.append({
                                'url': raw_result.get('url'),
                                'title': raw_result.get('title'),
                                'quality': quality,
                                'tokens': processed_result.get('token_count', 0),
                                'content_length': len(processed_result.get('content', ''))
                            })
                            
                        else:
                            if detailed:
                                print(f"⚠️  内容质量不合格，已过滤")
                            filtered_count += 1
                            performance_stats['failed_requests'] += 1
                            
                    except Exception as proc_error:
                        if detailed:
                            print(f"❌ 内容处理失败: {proc_error}")
                        performance_stats['failed_requests'] += 1
                
                # 关键词级统计
                keyword_total_time = time.time() - keyword_start_time
                
                if detailed:
                    print(f"\n📊 关键词 '{keyword}' 最终统计:")
                    print(f"- 总耗时: {keyword_total_time:.2f}秒")
                    print(f"- 搜索耗时: {search_time:.2f}秒")
                    print(f"- 处理耗时: {keyword_total_time - search_time:.2f}秒")
                    print(f"- 有效结果: {successful_count}/{len(raw_results)} 个")
                    if filtered_count > 0:
                        print(f"- 质量过滤: {filtered_count} 个")
                    print(f"- 总Token数: {keyword_tokens:,}")
                
                performance_stats['keyword_times'].append({
                    'keyword': keyword,
                    'total_time': keyword_total_time,
                    'search_time': search_time,
                    'process_time': keyword_total_time - search_time,
                    'raw_results': len(raw_results),
                    'successful_results': successful_count,
                    'filtered_results': filtered_count,
                    'tokens': keyword_tokens
                })
                
                performance_stats['successful_requests'] += successful_count
                performance_stats['total_tokens'] += keyword_tokens
                all_results.extend(processed_results)
                
            except Exception as e:
                keyword_total_time = time.time() - keyword_start_time
                print(f"❌ 关键词 '{keyword}' 处理出错: {e}")
                print(f"   总耗时: {keyword_total_time:.2f}秒")
                performance_stats['failed_requests'] += 1
                performance_stats['keyword_times'].append({
                    'keyword': keyword,
                    'total_time': keyword_total_time,
                    'error': str(e)
                })
        
        # 总体统计
        total_time = time.time() - total_start_time
        performance_stats['total_time'] = total_time
        
        # 工具内部统计
        tool_stats = search_tool.get_stats()
        processor_stats = processor.stats
        
        print(f"\n{'='*60}")
        print(f"🎯 整体性能报告")
        print(f"{'='*60}")
        print(f"- 总耗时: {total_time:.2f}秒")
        print(f"- 平均每个关键词耗时: {total_time/len(keywords):.2f}秒")
        print(f"- 是否在时间限制内: {'✅ 是' if total_time <= 60 else '❌ 否'}")
        
        # 详细统计
        print(f"\n📊 内容处理统计:")
        print(f"- 原始请求数: {performance_stats['successful_requests'] + performance_stats['failed_requests']}")
        print(f"- 有效结果数: {performance_stats['successful_requests']}")
        print(f"- 失败请求数: {performance_stats['failed_requests']}")
        print(f"- 总Token数: {performance_stats['total_tokens']:,}")
        
        if performance_stats['successful_requests'] > 0:
            avg_tokens = performance_stats['total_tokens'] / performance_stats['successful_requests']
            print(f"- 平均每结果Token数: {avg_tokens:.0f}")
        
        # 质量分布
        print(f"\n📈 内容质量分布:")
        quality_dist = performance_stats['quality_stats']
        total_quality = sum(quality_dist.values())
        if total_quality > 0:
            print(f"- 优秀 (Excellent): {quality_dist['excellent']} ({quality_dist['excellent']/total_quality*100:.1f}%)")
            print(f"- 良好 (Good): {quality_dist['good']} ({quality_dist['good']/total_quality*100:.1f}%)")
            print(f"- 一般 (Fair): {quality_dist['fair']} ({quality_dist['fair']/total_quality*100:.1f}%)")
            print(f"- 较差 (Poor): {quality_dist['poor']} ({quality_dist['poor']/total_quality*100:.1f}%)")
        
        # 工具性能统计
        print(f"\n🔧 工具性能统计:")
        print(f"- API总请求数: {tool_stats['total_requests']}")
        print(f"- 缓存命中数: {tool_stats['cache_hits']}")
        print(f"- 缓存命中率: {tool_stats['cache_hit_rate']}")
        print(f"- 请求错误数: {tool_stats['errors']}")
        print(f"- 当前缓存大小: {tool_stats['current_cache_size']}")
        
        # 各阶段耗时详情
        print(f"\n⏱️  各关键词处理详情:")
        for stat in performance_stats['keyword_times']:
            if 'error' in stat:
                print(f"- '{stat['keyword']}': {stat['total_time']:.2f}秒 (❌ 错误)")
            else:
                print(f"- '{stat['keyword']}': 总{stat['total_time']:.2f}秒 "
                      f"(搜索{stat['search_time']:.2f}s + 处理{stat['process_time']:.2f}s) "
                      f"✅ {stat['successful_results']}/{stat['raw_results']} 有效")
        
        # 性能评估
        success_rate = (performance_stats['successful_requests'] / 
                       max(performance_stats['successful_requests'] + performance_stats['failed_requests'], 1)) * 100
        
        print(f"\n🏆 性能评估:")
        if total_time <= 30:
            perf_rating = "优秀 ⭐⭐⭐"
        elif total_time <= 60:
            perf_rating = "良好 ⭐⭐"
        else:
            perf_rating = "需优化 ⭐"
        
        print(f"- 时间效率: {perf_rating} ({total_time:.2f}秒)")
        print(f"- 内容成功率: {success_rate:.1f}%")
        
        if quality_dist['excellent'] + quality_dist['good'] > quality_dist['fair'] + quality_dist['poor']:
            quality_rating = "优质内容占主导 ✅"
        else:
            quality_rating = "内容质量有待提升 ⚠️"
        print(f"- 内容质量: {quality_rating}")
        
        overall_success = (total_time <= 60 and 
                          performance_stats['successful_requests'] > 0 and
                          success_rate >= 70)
        
        print(f"\n🎯 综合评价: {'✅ 通过' if overall_success else '❌ 未通过'}")
        
        return {
            'total_time': total_time,
            'stats': performance_stats,
            'tool_stats': tool_stats,
            'processor_stats': processor_stats,
            'results': all_results,
            'success': overall_success,
            'success_rate': success_rate
        }
        
    except ImportError as e:
        print(f"❌ 无法导入ProductionReadyJinaTool: {e}")
        print("请检查agent_tools/tool_jina_search.py文件是否存在")
        return None
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Jina Search工具性能测试')
    parser.add_argument('keywords', nargs='*', help='要检索的中文关键词')
    parser.add_argument('--default', action='store_true', help='使用默认关键词测试')
    parser.add_argument('--concurrent', action='store_true', help='启用并发测试模式')
    parser.add_argument('--env-file', default='.env', help='环境变量文件路径')
    parser.add_argument('--output', help='输出结果到JSON文件')
    
    args = parser.parse_args()
    
    # 处理关键词输入
    if args.keywords:
        test_keywords = args.keywords
    elif args.default:
        test_keywords = ["半导体", "新能源", "人工智能"]
    else:
        # 交互式输入
        user_input = input("请输入要测试的中文关键词（用逗号分隔）: ").strip()
        if user_input:
            test_keywords = [kw.strip() for kw in user_input.split(',')]
        else:
            test_keywords = ["半导体", "新能源", "人工智能"]
    
    # 执行测试
    result = test_jina_search_tool(test_keywords, concurrent=args.concurrent)
    
    # 输出结果摘要
    if result:
        print(f"\n📋 测试总结:")
        print(f"- 总耗时: {result['total_time']:.2f}秒")
        print(f"- 成功率: {result['success_rate']:.1f}%")
        print(f"- 测试状态: {'✅ 通过' if result['success'] else '❌ 未通过'}")
        
        if result['success']:
            print(f"\n✅ 测试通过！Jina Search工具性能符合要求")
            print(f"   🎯 推荐用于生产环境")
        else:
            print(f"\n❌ 测试未通过，请检查以下方面：")
            if result['total_time'] > 60:
                print(f"   ⏱️  响应时间过长，请优化网络或调整超时设置")
            if result['success_rate'] < 70:
                print(f"   🔍 内容获取成功率偏低，请检查API配置或关键词")
            
        # 如果指定了输出文件
        if args.output:
            import json
            output_data = {
                'test_time': datetime.now().isoformat(),
                'keywords': test_keywords,
                'concurrent': args.concurrent,
                'total_time': result['total_time'],
                'success_rate': result['success_rate'],
                'success': result['success'],
                'stats': result['stats'],
                'tool_stats': result['tool_stats'],
                'processor_stats': result['processor_stats']
            }
            
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            print(f"\n💾 测试结果已保存到: {args.output}")

if __name__ == "__main__":
    main()