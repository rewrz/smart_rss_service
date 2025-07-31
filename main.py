import os
import json

import logging
import threading, os
from functools import wraps
from flask import Flask, send_from_directory, request, render_template, redirect, url_for, flash, Response, session
from dotenv import load_dotenv, set_key, find_dotenv
from flask_wtf import FlaskForm
from wtforms import PasswordField
from wtforms.validators import DataRequired
from werkzeug.security import check_password_hash, generate_password_hash
import feedparser
from apscheduler.schedulers.background import BackgroundScheduler
from time import strftime

from feed_fetcher import verify_feed_url
from feed_fetcher import fetch_all_feeds
from llm_processor import filter_articles_with_llm
from rss_generator import create_rss_feed

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
scheduler = BackgroundScheduler(daemon=True)
# 加载环境变量 (GEMINI_API_KEY)
load_dotenv()

app = Flask(__name__)
# 密钥配置: 必须在生产环境中设置为一个固定的、随机的、保密的值
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))
if app.secret_key == os.urandom(24):
    logging.warning("FLASK_SECRET_KEY not set, using a temporary key. User sessions will not persist across restarts.")

# 密码配置: 从环境变量加载哈希后的密码
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")
if not ADMIN_PASSWORD_HASH:
    logging.error("FATAL: ADMIN_PASSWORD_HASH is not set in the .env file. The application cannot start securely.")
    # 在实际部署中，你可能希望在这里退出程序
    # exit(1)

@app.context_processor
def utility_processor():
    """向模板上下文注入实用函数，使其在所有模板中可用。"""
    return dict(strftime=strftime)

# --- 认证相关 ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/verify_feeds', methods=['POST'])
@login_required
def verify_feeds_route():
    """处理一键检查所有RSS源的请求。"""
    urls = request.json.get('urls', [])
    results = {}
    for url in urls:
        if not url:
            continue
        is_valid = verify_feed_url(url)
        results[url] = is_valid
        status = "有效" if is_valid else "失效"
        logging.info(f"验证URL: {url} -> {status}")
    return json.dumps(results)

# 用于防止重复更新的全局锁
update_in_progress = threading.Lock()

# --- 表单定义 ---
class LoginForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired()])

class SettingsForm(FlaskForm):
    # 这个表单只用于CSRF保护，字段在HTML中手动渲染
    pass

class UpdateForm(FlaskForm):
    # 空表单，仅用于“立即更新”按钮的CSRF保护
    pass

class ClearCacheForm(FlaskForm):
    # 空表单，仅用于“清除缓存”按钮的CSRF保护
    pass


def load_config():
    """从config.json加载配置"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # 如果配置文件不存在，返回一个默认结构以避免错误
        logging.warning("config.json not found. Using default structure.")
        return {
            "source_feeds": [],
            "user_interests": "",
            "priority_keywords": [],
            "llm_api_endpoint": "",
            "llm_model_name": "local-model",
            "output_file": "smart_rss.xml",
            "server_port": 8000,
            "update_interval_hours": 1,
            "priority_max_days": 30,
            "interest_max_days": 3,
            "cache_retention_days": 30,
            "output_feed_details": {
                "title": "来自「我的信息结界」的情报",
                "link": "http://localhost:8000",
                "description": "由专属AI守护，过滤全网信息，只为你呈现最核心的内容。"
            }
        }

def save_config(config_data):
    """将配置数据写入config.json文件"""
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)

def run_update_process():
    """执行完整的更新流程"""
    if not update_in_progress.acquire(blocking=False):
        logging.info("更新流程已在进行中，本次调度跳过。")
        return

    logging.info("开始执行RSS源更新流程...")
    config = load_config()
    api_key = os.getenv("GEMINI_API_KEY")
    api_url = config.get("llm_api_endpoint")
    model_name = config.get("llm_model_name", "local-model") # 从配置加载模型名称，提供默认值

    if not api_key:
        logging.error("错误: API Key未设置。")
        update_in_progress.release()
        return

    if not api_url or not config.get('source_feeds'):
        logging.error("错误: API端点或RSS源未配置。请检查设置页面。")
        update_in_progress.release()
        return

    try:
        # 1. 抓取所有源，并应用缓存和时效性过滤
        new_articles = fetch_all_feeds(
            feed_sources=config['source_feeds'],
            priority_max_days=config.get('priority_max_days', 30),
            interest_max_days=config.get('interest_max_days', 3),
            cache_retention_days=config.get('cache_retention_days', 30)
        )

        # 2. 使用LLM筛选
        selected_articles = filter_articles_with_llm(new_articles, config['user_interests'], config.get('priority_keywords', []), api_key, api_url, model_name)

        # 3. 生成新的RSS文件
        create_rss_feed(selected_articles, config['output_file'], config.get('output_feed_details', {}))
        logging.info(f"流程完成！新的RSS文件已生成在 {config['output_file']}")
    finally:
        update_in_progress.release()

@app.route('/')
def index():
    """渲染主着陆页。"""
    # 生成供页面显示的订阅链接URL
    feed_url = url_for('serve_rss_feed', _external=True)
    config = load_config()
    output_file = config.get('output_file', 'smart_rss.xml')
    
    articles = []
    feed_exists = os.path.exists(config.get('output_file', 'smart_rss.xml'))

    if feed_exists:
        # 解析已生成的RSS文件以获取内容
        feed = feedparser.parse(output_file)
        articles = feed.entries

    return render_template('index.html', feed_url=feed_url, feed_exists=feed_exists, articles=articles)

@app.route('/feed.xml')
def serve_rss_feed():
    """提供生成的RSS XML文件。"""
    config = load_config()
    output_file = config.get('output_file', 'smart_rss.xml')
    if not os.path.exists(output_file):
        return "订阅源尚未生成。请访问主页，登录并完成设置。", 404
    return send_from_directory('.', output_file, mimetype='application/rss+xml')


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """管理配置的Web界面"""
    settings_form = SettingsForm()
    update_form = UpdateForm() # 为“立即更新”按钮准备表单
    clear_cache_form = ClearCacheForm() # 为“清除缓存”按钮准备表单

    if settings_form.validate_on_submit(): # 仅在提交“保存设置”表单时为True
        config = load_config()

        # 从表单更新配置
        # Handle the new structured source_feeds
        source_feeds = []
        feed_names = request.form.getlist('feed_name')
        feed_urls = request.form.getlist('feed_url')
        for name, url in zip(feed_names, feed_urls):
            if name.strip() and url.strip():
                source_feeds.append({'name': name.strip(), 'url': url.strip()})
        config['source_feeds'] = source_feeds

        config['user_interests'] = request.form['user_interests']
        config['update_interval_hours'] = int(request.form.get('update_interval_hours', 1))
        config['priority_keywords'] = [kw.strip() for kw in request.form['priority_keywords'].splitlines() if kw.strip()]
        config['priority_max_days'] = int(request.form.get('priority_max_days', 30))
        config['interest_max_days'] = int(request.form.get('interest_max_days', 3))
        config['cache_retention_days'] = int(request.form.get('cache_retention_days', 30))
        config['llm_api_endpoint'] = request.form['llm_api_endpoint']
        config['llm_model_name'] = request.form.get('llm_model_name', 'local-model')
        
        save_config(config)
        # 重新调度任务以应用新的时间间隔
        reschedule_update_task(config['update_interval_hours'])

        messages = ['设置已成功保存！']
        # 如果提供了新的API密钥，则更新.env文件
        new_api_key = request.form.get('api_key')
        if new_api_key:
            env_file = find_dotenv()
            if not env_file:
                env_file = '.env' # 如果.env文件不存在则创建
            set_key(env_file, "GEMINI_API_KEY", new_api_key)
            load_dotenv(override=True) # 重新加载环境变量
            messages.append('API密钥已一并更新。')
        
        messages.append('后台更新任务已启动。')
        flash(' '.join(messages), 'success')
        thread = threading.Thread(target=run_update_process)
        thread.start()
        return redirect(url_for('settings'))

    # 对于GET请求，加载并显示当前配置，并将两个表单对象传递给模板
    config = load_config()
    return render_template('settings.html', config=config, form=settings_form, update_form=update_form, clear_cache_form=clear_cache_form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if not ADMIN_PASSWORD_HASH:
        flash("应用未配置密码，无法登录。请联系管理员。")
        return render_template('login.html', form=LoginForm()), 500

    form = LoginForm()
    if form.validate_on_submit():
        if check_password_hash(ADMIN_PASSWORD_HASH, form.password.data):
            session['logged_in'] = True
            flash('登录成功！', 'success')
            return redirect(url_for('settings'))
        else:
            flash('密码错误！')
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('您已成功退出。')
    return redirect(url_for('login'))

@app.route('/update', methods=['POST'])
@login_required
def trigger_update():
    """触发后台更新流程"""
    form = UpdateForm()
    if not form.validate_on_submit():
        flash('无效的更新请求或CSRF令牌已过期。', 'error')
        return redirect(url_for('settings'))

    thread = threading.Thread(target=run_update_process)
    thread.start()
    flash('RSS源更新流程已在后台启动。处理需要一些时间，请稍后刷新主页查看结果。', 'success')
    return redirect(url_for('settings'))

@app.route('/clear_cache', methods=['POST'])
@login_required
def clear_cache():
    """清除文章缓存文件。"""
    form = ClearCacheForm()
    if not form.validate_on_submit():
        flash('无效的请求或CSRF令牌已过期。', 'error')
        return redirect(url_for('settings'))

    cache_file = 'article_cache.json'
    if os.path.exists(cache_file):
        try:
            os.remove(cache_file)
            flash('文章缓存已成功清除！下次更新时将重新处理所有文章。', 'success')
            logging.info("Article cache file 'article_cache.json' was manually cleared.")
        except OSError as e:
            flash(f'清除缓存时出错: {e}', 'error')
            logging.error(f"Error clearing cache file {cache_file}: {e}")
    else:
        flash('缓存文件不存在，无需清除。', 'info')
    return redirect(url_for('settings'))

def reschedule_update_task(hours):
    """重新安排后台更新任务。"""
    # 使用 add_job 并设置 replace_existing=True，这是更健壮的方式。
    # 它会替换现有任务，或者如果任务不存在则创建它，从而避免 JobLookupError。
    scheduler.add_job(
        run_update_process,
        'interval',
        hours=hours,
        id='daily_update',
        replace_existing=True
    )
    logging.info(f"自动更新任务已重新调度，频率为每 {hours} 小时一次。")

if __name__ == '__main__':
    config = load_config()
    
    # 初始化并启动调度器
    update_interval = config.get("update_interval_hours", 1)
    # 给任务一个唯一的ID，方便之后重新调度
    scheduler.add_job(
        run_update_process, 
        'interval', 
        hours=update_interval, 
        id='daily_update'
    )
    scheduler.start()
    logging.info(f"服务启动，自动更新已设置为每 {update_interval} 小时运行一次。")

    app.run(host='0.0.0.0', port=config.get('server_port', 8000), use_reloader=False)