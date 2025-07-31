from feedgen.feed import FeedGenerator
from datetime import datetime
import pytz

def create_rss_feed(articles: list, output_path: str, feed_config: dict):
    """
    根据文章列表创建一个RSS文件。

    Args:
        articles: 包含筛选后文章的字典列表。
        output_path: 生成的RSS文件的保存路径。
        feed_config: 包含RSS feed元数据（如标题、链接、描述）的字典。
    """
    fg = FeedGenerator()
    fg.title(feed_config.get('title', 'Personalized AI RSS Feed'))
    fg.link(href=feed_config.get('link', 'http://localhost'), rel='alternate')
    fg.description(feed_config.get('description', 'Articles filtered by AI based on my interests.'))
    fg.language('zh-CN')

    for article in articles:
        fe = fg.add_entry()

        title = article['title']
        reason = article.get('selection_reason')
        # 如果文章是因优先关注而被选中，则在标题前添加标记
        if reason and reason != 'interest':
            title = f"[{reason}] {title}"
        fe.title(title)
        fe.link(href=article['link'])
        fe.description(article['summary'])
        
        # 处理发布日期
        if article['published']:
            # feedgen需要时区信息的datetime对象
            pub_date = datetime(*article['published'][:6])
            fe.pubDate(pytz.UTC.localize(pub_date))

    fg.rss_file(output_path, pretty=True)