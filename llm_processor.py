import requests
import logging
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def filter_articles_with_llm(articles: list, user_interests: str, priority_keywords: list, api_key: str, api_url: str, model_name: str) -> list:
    """
    使用LLM根据用户兴趣筛选文章，支持Gemini和OpenAI兼容的API。

    Args:
        articles: 待筛选的文章列表。
        user_interests: 描述用户兴趣的字符串。
        priority_keywords: 优先关注的关键词列表。
        api_key: API密钥。
        api_url: LLM API的端点URL。
        model_name: (可选) 用于OpenAI兼容API的模型名称。

    Returns:
        一个经过筛选，符合用户兴趣的文章列表。
    """
    if not api_key:
        raise ValueError("API Key未设置。")
    if not api_url:
        raise ValueError("LLM API Endpoint未在配置中设置。")

    # 根据URL判断API类型
    api_type = "gemini" if "gemini" in api_url.lower() else "openai"
    logging.info(f"检测到API类型: {api_type}")
    
    selected_articles = []
    chunk_size = 10  # 每次处理10篇文章，防止超出上下文长度

    logging.info(f"开始使用LLM筛选文章，共 {len(articles)} 篇，每批处理 {chunk_size} 篇。")

    for i in range(0, len(articles), chunk_size):
        chunk = articles[i:i + chunk_size]
        
        priority_keywords_str = ", ".join([f'"{kw}"' for kw in priority_keywords])
        base_prompt = f"""你是一个智能信息分析助手，任务是从文章列表中为我筛选出我应该阅读的内容。请仔细评估每一篇文章，确保不会错过任何重要或我感兴趣的内容。

筛选标准分为两级：
1.  **优先关注**: 任何内容与以下关键词高度相关的文章都必须被选中：[{priority_keywords_str}]。
2.  **通用兴趣**: 如果文章不属于优先关注，再判断其内容是否符合我的通用兴趣：“{user_interests}”。

**输出要求**:
你必须返回一个JSON对象，其唯一的键是 "selected_articles"，值是一个对象数组。
- 每个对象代表一篇被选中的文章，并必须包含 `index` (文章在列表中的原始索引) 和 `reason`。
- 如果因“优先关注”被选中，`reason` 必须是命中的那个关键词。
- 如果因“通用兴趣”被选中，`reason` 必须是字符串 "interest"。
- 如果没有任何文章符合标准，则返回 {{"selected_articles": []}}。

**输出格式示例**:
```json
{{
  "selected_articles": [
    {{ "index": 1, "reason": "地震" }},
    {{ "index": 4, "reason": "interest" }}
  ]
}}
```

**待分析的文章列表**:
        """
        for idx, article in enumerate(chunk):
            # 增加摘要长度，为LLM提供更多上下文以做出更准确的判断
            summary_text = article.get('summary', '')
            base_prompt += f"\n{idx}. 标题: {article['title']}\n   摘要: {summary_text[:500]}...\n"

        prompt = base_prompt
        # 根据API类型构建不同的prompt和payload
        if api_type == "gemini":
            full_api_url = f"{api_url}?key={api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
        else:  # openai compatible
            full_api_url = api_url
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            payload = {
                "model": model_name,  # 对于本地模型或兼容API，此名称可能是必需的
                "messages": [{"role": "user", "content": prompt}],
            }

        try:
            logging.info(f"正在处理第 {i//chunk_size + 1} 批文章 (API: {api_type})...")
            
            response = requests.post(full_api_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()  # 如果请求失败 (状态码 4xx or 5xx), 则会抛出异常
            
            response_data = response.json()
            response_text = ""

            # 根据API类型解析响应
            if api_type == "gemini":
                if response_data.get('candidates') and response_data['candidates'][0].get('content', {}).get('parts'):
                    response_text = response_data['candidates'][0]['content']['parts'][0]['text']
                else:
                    logging.error(f"Gemini响应格式不完整或为空: {response_data}")
                    continue
            else: # openai
                if response_data.get('choices') and response_data['choices'][0].get('message', {}).get('content'):
                    response_text = response_data['choices'][0]['message']['content']
                else:
                    logging.error(f"OpenAI响应格式不完整或为空: {response_data}")
                    continue
            
            # 清理并解析LLM返回的JSON
            cleaned_text = response_text.strip()
            # 从Markdown代码块中提取JSON
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:].strip()
            elif cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:].strip()
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3].strip()
            if cleaned_text.startswith("json"):
                cleaned_text = cleaned_text[4:].strip()

            # 根据API类型解析JSON内容
            json_data = json.loads(cleaned_text)
            selections = json_data.get("selected_articles", [])
            
            logging.info(f"LLM返回的筛选结果: {selections}")

            for selection in selections:
                index = selection.get('index')
                reason = selection.get('reason')
                if isinstance(index, int) and 0 <= index < len(chunk) and reason:
                    selected_article = chunk[index]
                    selected_article['selection_reason'] = reason
                    selected_articles.append(selected_article)
        except json.JSONDecodeError:
            logging.error(f"无法解析LLM的响应为JSON: {response_text}")
        except requests.exceptions.RequestException as e:
            logging.error(f"请求LLM API时出错: {e}")
        except Exception as e:
            logging.error(f"处理第 {i//chunk_size + 1} 批文章时发生未知错误: {e}")

    logging.info(f"筛选完成，共选出 {len(selected_articles)} 篇感兴趣的文章。")
    return selected_articles