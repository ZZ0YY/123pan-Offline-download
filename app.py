# app.py
import os
import json
import time
import requests
from flask import Flask, render_template, url_for, flash, jsonify, request, redirect
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime

# --- 初始化和配置 ---
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'a-very-secret-key-for-dev-use-only')

CONFIG_FILE = 'config.json'
# 定义根域名，方便拼接不同的API路径
API_DOMAIN = 'https://open-api.123pan.com' 

# --- 内存缓存 ---
# 用于在内存中缓存access_token，避免每次请求都读取文件
_token_cache = {
    'accessToken': None,
    'expired_at_ts': 0  # 存储为Unix时间戳，方便比较
}

# --- 配置持久化核心函数 ---
def load_config():
    """从 config.json 加载配置"""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_config(data):
    """将配置保存到 config.json"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        print(f"Error saving config file: {e}")

# --- Token管理核心函数 (已优化) ---
def get_access_token():
    """
    获取或刷新access_token。
    优化流程：优先检查内存缓存 -> 检查文件 -> 最后才请求API。
    """
    # 1. 优先检查内存缓存
    if _token_cache['accessToken'] and time.time() < _token_cache['expired_at_ts'] - 300:
        return _token_cache['accessToken']

    # 2. 内存缓存无效，检查配置文件
    config = load_config()
    client_id, client_secret = config.get('clientID'), config.get('clientSecret')
    if not client_id or not client_secret:
        return None

    expired_at_str = config.get('expiredAt')
    if expired_at_str:
        try:
            expired_dt = datetime.fromisoformat(expired_at_str)
            expired_timestamp = expired_dt.timestamp()
            if time.time() < expired_timestamp - 300:
                # 成功获取Token后，更新内存缓存
                _token_cache['accessToken'] = config['accessToken']
                _token_cache['expired_at_ts'] = expired_timestamp
                return config['accessToken']
        except (ValueError, TypeError):
            pass

    # 4. 文件中的Token也无效，刷新Token
    print("Refreshing token from API...")
    response = requests.post(
        f"{API_DOMAIN}/api/v1/access_token",
        headers={'Platform': 'open_platform', 'Content-Type': 'application/json'},
        json={'clientID': client_id, 'clientSecret': client_secret}
    )

    if response.status_code == 200 and response.json().get('code') == 0:
        data = response.json()['data']
        new_token, new_expired_at_str = data['accessToken'], data['expiredAt']
        
        # 更新配置文件
        config['accessToken'] = new_token
        config['expiredAt'] = new_expired_at_str
        save_config(config)

        # 更新内存缓存
        try:
            new_expired_dt = datetime.fromisoformat(new_expired_at_str)
            _token_cache['accessToken'] = new_token
            _token_cache['expired_at_ts'] = new_expired_dt.timestamp()
        except (ValueError, TypeError):
             _token_cache['expired_at_ts'] = 0

        print("Successfully refreshed and saved token.")
        return new_token
    
    print(f"Failed to refresh token. Response: {response.text}")
    # 获取失败，清空缓存
    _token_cache['accessToken'], _token_cache['expired_at_ts'] = None, 0
    return None

# --- 装饰器与API请求封装 ---
def credentials_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not get_access_token():
            flash('凭证无效或已过期，请重新配置。', 'error')
            return redirect(url_for('configure'))
        return f(*args, **kwargs)
    return decorated_function

def api_request(method, endpoint, **kwargs):
    token = get_access_token()
    if not token: return None

    headers = {'Authorization': f"Bearer {token}", 'Platform': 'open_platform', 'Content-Type': 'application/json'}
    try:
        response = requests.request(method, f"{API_DOMAIN}{endpoint}", headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
        return None
        
# --- 核心路由 ---
@app.route('/', methods=['GET', 'POST'])
def configure():
    config = load_config()
    if request.method == 'POST':
        client_id, client_secret = request.form.get('client_id'), request.form.get('client_secret')
        if not client_id or not client_secret:
            flash('Client ID 和 Client Secret 均不能为空。', 'error')
            return render_template('configure.html')
        # 临时保存以供 get_access_token 使用
        save_config({'clientID': client_id, 'clientSecret': client_secret})
        # 清除旧的内存缓存，强制重新获取
        _token_cache['accessToken'], _token_cache['expired_at_ts'] = None, 0
        if get_access_token():
            flash('凭证已验证并成功保存！', 'success')
            final_config = load_config()
            if 'task_ids' not in final_config: final_config['task_ids'] = []
            save_config(final_config)
            return redirect(url_for('dashboard'))
        else:
            save_config(config) # 验证失败，恢复旧配置
            flash('提供的凭证无效，请重新检查并提交。', 'error')
            return render_template('configure.html')
    if get_access_token(): return redirect(url_for('dashboard'))
    return render_template('configure.html')

@app.route('/dashboard')
@credentials_required
def dashboard(): return render_template('dashboard.html')

@app.route('/add_tasks', methods=['POST'])
@credentials_required
def add_tasks():
    links_text = request.form.get('links')
    dir_id = request.form.get('dirID')
    links = [link.strip() for link in links_text.splitlines() if link.strip()]
    if not links:
        flash('下载链接不能为空。', 'error')
        return redirect(url_for('dashboard'))
    config = load_config()
    task_ids = config.get('task_ids', [])
    added_count = 0
    for link in links:
        payload = {'url': link}
        if dir_id and dir_id.isdigit(): payload['dirID'] = int(dir_id)
        result = api_request('post', '/api/v1/offline/download', json=payload)
        if result and result.get('code') == 0:
            task_id = result['data']['taskID']
            if task_id not in task_ids: task_ids.append(task_id)
            added_count += 1
    config['task_ids'] = task_ids
    save_config(config)
    flash(f"成功添加 {added_count} / {len(links)} 个离线任务。", 'success')
    return redirect(url_for('dashboard'))

@app.route('/api/get_folders')
@credentials_required
def get_folders():
    parent_id = request.args.get('parent_id', 0)
    all_folders = []
    last_file_id = 0
    while True:
        params = {'parentFileId': parent_id, 'limit': 100}
        if last_file_id != 0: params['lastFileId'] = last_file_id
        list_data = api_request('get', '/api/v2/file/list', params=params)
        if not (list_data and list_data.get('code') == 0):
            return jsonify({"error": "Failed to fetch folders"}), 500
        data = list_data.get('data', {})
        file_list = data.get('fileList', [])
        for item in file_list:
            if item['type'] == 1 and item.get('trashed', 0) == 0:
                all_folders.append({"id": item['fileId'], "name": item['filename']})
        last_file_id = data.get('lastFileId', -1)
        if last_file_id == -1: break
    return jsonify(all_folders)

@app.route('/api/create_folder', methods=['POST'])
@credentials_required
def create_folder():
    data = request.get_json()
    folder_name = data.get('name')
    parent_id = data.get('parentID')

    if not folder_name or parent_id is None:
        return jsonify({"error": "Missing folder name or parent ID"}), 400

    payload = {'name': folder_name, 'parentID': int(parent_id)}
    result = api_request('post', '/upload/v1/file/mkdir', json=payload)
    
    if result and result.get('code') == 0:
        return jsonify(result['data']), 201 # 201 Created
    elif result:
        return jsonify({"error": result.get('message', 'Failed to create folder'), "api_response": result}), 400
    else:
        return jsonify({"error": "Failed to create folder due to a server or network error"}), 500

@app.route('/api/tasks_status')
@credentials_required
def get_tasks_status():
    task_ids = load_config().get('task_ids', [])
    if not task_ids: return jsonify({})
    status_map = {}
    for task_id in task_ids:
        progress_data = api_request('get', '/api/v1/offline/download/process', params={'taskID': task_id})
        if progress_data and progress_data.get('code') == 0:
            status_map[task_id] = progress_data['data']
        else:
            status_map[task_id] = {'status': -1, 'process': 0, 'statusText': '查询失败'}
    return jsonify(status_map)

@app.route('/api/clear_completed_tasks', methods=['POST'])
@credentials_required
def clear_completed_tasks():
    config = load_config()
    task_ids = config.get('task_ids', [])
    if not task_ids: return jsonify({"message": "No tasks to clear."})
    active_tasks = []
    for task_id in task_ids:
        progress_data = api_request('get', '/api/v1/offline/download/process', params={'taskID': task_id})
        if progress_data and progress_data.get('code') == 0:
            status = progress_data['data'].get('status')
            if status not in [1, 2]: active_tasks.append(task_id)
        else:
            active_tasks.append(task_id)
    cleared_count = len(task_ids) - len(active_tasks)
    config['task_ids'] = active_tasks
    save_config(config)
    flash(f"已清理 {cleared_count} 个已完成的任务。", 'info')
    return jsonify({"message": f"Cleared {cleared_count} completed tasks."})

@app.route('/reset')
def reset_config():
    if os.path.exists(CONFIG_FILE): os.remove(CONFIG_FILE)
    _token_cache['accessToken'], _token_cache['expired_at_ts'] = None, 0
    flash('配置已清除。请重新输入您的凭证。', 'info')
    return redirect(url_for('configure'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)