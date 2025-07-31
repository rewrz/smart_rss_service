import feedparser
import logging
import requests
import json
import os
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CACHE_FILE = 'article_cache.json'

def load_cache():
    """
    从文件加载缓存。
    """
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_cache(cache_data):
    """
    将缓存保存到文件。
    """
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)

def clean_cache(cache_data, retention_days):
    """
    从缓存中移除比指定天数更早的旧条目。
    """
    if not cache_data:
        return cache_data
    
    cleaned_cache = {}
    retention_limit = datetime.now(timezone.utc) - timedelta(days=retention_days)
    
    for key, value in cache_data.items():
        try:
            # 假设缓存的值是一个包含 'cached_at' 时间戳的字典
            cached_at = datetime.fromisoformat(value['cached_at'])
            if cached_at > retention_limit:
                cleaned_cache[key] = value
        except (TypeError, KeyError, ValueError):
            # 如果条目格式不正确，则忽略
            continue
            
    return cleaned_cache

def fetch_all_feeds(feed_sources: list, priority_max_days: int, interest_max_days: int, cache_retention_days: int) -> list:
    """
    抓取多个RSS订阅源，合并文章，并根据时效性和缓存进行过滤。

    Args:
        feed_urls: RSS源URL列表。
        priority_max_days: 优先关注文章的最大保留天数。
        interest_max_days: 通用兴趣文章的最大保留天数。
        cache_retention_days: 缓存中文章的最大保留天数。

    Returns:
        一个只包含新的、未被缓存且符合时效的文章的列表。
    """
    cache = load_cache()
    cache = clean_cache(cache, cache_retention_days)
    
    new_articles = []
    now = datetime.now(timezone.utc)
    max_age_days = max(priority_max_days, interest_max_days)
    
    logging.info(f"开始从 {len(feed_sources)} 个源抓取文章，将过滤掉超过 {max_age_days} 天的文章...")

    for source in feed_sources:
        url = source.get('url')
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                # 1. 时效性过滤
                published_time = entry.get('published_parsed')
                if not published_time:
                    continue # 跳过没有发布日期的文章
                
                # 将feedparser的时间元组转换为带时区的datetime对象
                pub_date = datetime(*published_time[:6], tzinfo=timezone.utc)
                
                if (now - pub_date).days > max_age_days:
                    continue # 文章太旧，跳过

                # 2. 缓存过滤
                article_id = entry.get('id', entry.get('link'))
                if article_id in cache:
                    continue # 文章已在缓存中，跳过

                # 如果文章是新的且符合时效，则处理并加入列表
                new_articles.append({
                    'title': entry.get('title', 'No Title'),
                    'link': entry.get('link', ''),
                    'summary': entry.get('summary', ''),
                    'published': published_time,
                    'published_iso': pub_date.isoformat() # 保存ISO格式日期
                })
                
                # 将新文章加入缓存
                cache[article_id] = {'cached_at': now.isoformat()}

        except Exception as e:
            logging.error(f"抓取源 {url} 时出错: {e}")
            
    save_cache(cache)
    logging.info(f"抓取完成，发现 {len(new_articles)} 篇需要处理的新文章。")
    return new_articles

def verify_feed_url(url: str) -> bool:
    """通过尝试请求来验证一个RSS源URL是否有效。"""
    try:
        response = requests.get(url, headers={'User-Agent': 'MyInfoKekkai/1.0'}, timeout=10)
        response.raise_for_status()
        # 尝试解析以确保是有效的feed格式
        feed = feedparser.parse(response.content)
        return bool(feed.entries or feed.feed)
    except Exception:
        return False