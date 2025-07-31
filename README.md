# 我的信息结界 (Smart RSS Service)

`我的信息结界` 是一个智能 RSS 服务，旨在为你打造一个专属的、无噪音的信息获取环境。它利用大型语言模型（LLM）的强大能力，自动从你订阅的众多 RSS 源中筛选、分类和提炼出你真正关心和需要的内容，最终生成一个干净、个性化、高价值的 RSS 输出。

开发灵感来源于构建一个能抵御信息过载的“结界”。

![1](https://github.com/rewrz/smart_rss_service/blob/main/preview1.jpeg?raw=true)

![2](https://github.com/rewrz/smart_rss_service/blob/main/preview2.jpeg?raw=true)

![3](https://github.com/rewrz/smart_rss_service/blob/main/preview3.jpeg?raw=true)

## 核心特性

*   **多源聚合**: 支持添加任意数量的 RSS 订阅源。
*   **智能筛选**: 集成 LLM（支持 Gemini 和 OpenAI 兼容 API），根据你设定的“优先关键词”和“通用兴趣”描述，精准过滤文章。
*   **优先级标记**: 对于命中“优先关键词”的文章，在标题前自动添加标记（如 `[关键词]`），让你一目了然。
*   **Web界面管理**: 提供简洁的 Web UI，方便你随时登录、修改订阅源、调整兴趣偏好和各项配置。
*   **自动更新**: 内置定时任务，可按小时为单位自动在后台抓取和处理信息。
*   **安全可靠**: 管理页面通过密码保护，确保你的配置安全。
*   **缓存机制**: 自动缓存已处理的文章，避免重复处理，节省 LLM API 调用成本。

## 工作流程

1.  **抓取 (Fetch)**: `feed_fetcher.py` 定时从所有配置的 RSS 源抓取最新文章。
2.  **过滤 (Filter)**: `llm_processor.py` 将新文章打包，发送给指定的 LLM API，并根据返回的筛选结果（基于你的兴趣和关键词）选出文章。
3.  **生成 (Generate)**: `rss_generator.py` 将筛选后的文章生成一个新的、干净的 `smart_rss.xml` 文件。
4.  **服务 (Serve)**: `main.py` (Flask 应用) 提供 Web 管理界面，并向你的 RSS 阅读器提供最终生成的 `smart_rss.xml`。

## 部署与使用

### 第一步：准备环境

1.  **克隆项目**
    ```bash
    git clone https://github.com/rewrz/smart_rss_service.git
    cd smart_rss_service
    ```

2.  **创建并激活 Python 虚拟环境**
    ```bash
    # Windows
    python -m venv .venv
    .venv\Scripts\activate

    # Linux / macOS
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

### 第二步：创建 `.env` 配置文件

在项目根目录下创建一个名为 `.env` 的文件。这个文件用于存放你的敏感信息，如 API 密钥和密码。

1.  **生成管理员密码 (`ADMIN_PASSWORD_HASH`)**
    运行 `create_password.py` 脚本来生成密码的哈希值。
    ```bash
    python create_password.py
    ```
    根据提示输入你的管理员密码，然后将输出的 `ADMIN_PASSWORD_HASH="..."` 这一整行复制到 `.env` 文件中。

2.  **生成 Flask 密钥 (`FLASK_SECRET_KEY`)**
    这是一个用于加密会话（Session）的安全密钥。运行以下命令生成：
    ```bash
    # Linux / macOS
    python -c 'import secrets; print(secrets.token_hex(16))'

    # Windows
    python -c "import secrets; print(secrets.token_hex(16))"
    ```
    将生成的长字符串复制到 `.env` 文件中，作为 `FLASK_SECRET_KEY` 的值。

3.  **配置大模型 API 密钥 (`GEMINI_API_KEY`)**
    将你的大模型（如 Google Gemini 或其他 OpenAI 兼容服务）的 API 密钥填入。

4.  **最终的 `.env` 文件示例**
    你的 `.env` 文件现在应该看起来像这样：
    ```env
    # .env

    # 你的大模型API密钥 (项目内变量名为 GEMINI_API_KEY，但可用于任何兼容API)
    GEMINI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    # 用于会话加密的固定密钥
    FLASK_SECRET_KEY="a_very_long_and_random_string_generated_before"

    # 管理员密码的哈希值
    ADMIN_PASSWORD_HASH="scrypt:32768:8:1$xxxxxxxx$xxxxxxxx"
    ```

### 第三步：运行应用

根据你的操作系统，选择合适的命令来启动服务。

*   **生产环境 (Linux / macOS)**: 推荐使用 `gunicorn`。
    ```bash
    gunicorn --workers 4 --bind 0.0.0.0:8000 main:app
    ```

*   **生产环境 (Windows)**: 推荐使用 `waitress`。
    ```bash
    waitress-serve --host 0.0.0.0 --port 8000 main:app
    ```
服务启动后，你可以通过 `http://<你的服务器IP>:8000` 访问。

### 第四步：配置和使用

1.  **首次登录**: 访问 `http://<你的服务器IP>:8000/login`，输入你在第二步中设置的管理员密码。static 文件夹中添加或替换你自己的主页背景视频 background.mp4 文件。
2.  **进入设置**: 登录后，你将被重定向到设置页面。
3.  **填写配置**:
    *   **LLM API Endpoint**: 填写你的大模型服务商提供的 API 地址。
        *   **Google Gemini Pro**: `https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent`
        *   **OpenAI 兼容 API (如本地模型)**: `http://localhost:1234/v1/chat/completions`
    *   **LLM Model Name**: 如果你使用的是 OpenAI 兼容 API，请填写模型名称（例如 `local-model` 或 `gpt-4`）。对于 Gemini API，此项可留空。
    *   **RSS 订阅源**: 添加你想要监控的 RSS 源的名称和 URL。
    *   **优先关注关键词**: 每行一个。任何文章内容（标题或摘要）与这些词高度相关时，都将被无条件选中。
    *   **通用兴趣**: 用一段自然语言描述你的长期兴趣点，例如“我关注人工智能、AIGC的最新进展，特别是开源模型和技术应用。我也对个人知识管理、高效工作流和自动化工具感兴趣。”
    *   **其他参数**: 根据需要调整更新频率、文章保留天数等。
4.  **保存并启动**: 点击“保存设置”。系统会立即在后台启动一次更新流程。
5.  **获取你的专属 RSS**: 返回主页 (`http://<你的服务器IP>:8000`)，你将看到生成的专属 RSS 订阅链接。将此链接添加到你的 RSS 阅读器（如 Feedly, Inoreader, Reeder 等）即可开始享受过滤后的信息流！

## 项目作者

*   **博客**: https://rewrz.com/archive/llm-rss-cleaner
*   **GitHub**: @rewrz

## 许可

本项目采用 MIT 许可证。