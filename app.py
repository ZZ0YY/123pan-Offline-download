# app.py
import os
import requests
import time
from flask import Flask, session, render_template, url_for, flash, jsonify, request, redirect
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime

# --- 初始化和配置 ---
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'a-very-secret-key-for-dev-use-only')

CLIENT_ID_SESSION_KEY = 'client_id'
CLIENT_SECRET_SESSION_KEY = 'client_secret'
TOKEN_SESSION_KEY = 'access_token'
EXPIRED_AT_SESSION_KEY = 'token_expired_at'
TASK_IDS_SESSION_KEY = 'task_ids'

API_BASE_URL = 'https://open-api.123pan.com/api/v1'
API_V2_BASE_URL = 'https://open-api.123pan.com/api/v2'

# --- 全局缓存，用于存储路径到ID的映射 ---
DIR_ID_CACHE = {}

# --- Token管理核心函数 ---
def get_access_token():
    """使用存储在session中的用户凭证获取或刷新access_token。"""
    if CLIENT_ID_SESSION_KEY not in session or CLIENT_SECRET_SESSION_KEY not in session:
        return None

    expired_at_str = session.get(EXPIRED_AT_SESSION_KEY)
    if expired_at_str:
        try:
            expired_dt = datetime.fromisoformat(expired_at_str)
            expired_timestamp = expired_dt.timestamp()
            if time.time() < expired_timestamp - 300: # 提前5分钟刷新
                return session.get(TOKEN_SESSION_KEY)
        except (ValueError, TypeError):
            print(f"无法解析日期格式: {expired_at_str}")
            pass

    print("Refreshing token using user-provided credentials...")
    response = requests.post(
        f"{API_BASE_URL}/access_token",
        headers={'Platform': 'open_platform', 'Content-Type': 'application/json'},
        json={'clientID': session[CLIENT_ID_SESSION_KEY], 'clientSecret': session[CLIENT_SECRET_SESSION_KEY]}
    )

    if response.status_code == 200 and response.json().get('code') == 0:
        data = response.json()['data']
        session[TOKEN_SESSION_KEY] = data['accessToken']
        session[EXPIRED_AT_SESSION_KEY] = data['expiredAt']
        print("Successfully refreshed token.")
        return session[TOKEN_SESSION_KEY]
    
    # 获取失败，清除无效的凭证
    for key in [CLIENT_ID_SESSION_KEY, CLIENT_SECRET_SESSION_KEY, TOKEN_SESSION_KEY, EXPIRED_AT_SESSION_KEY]:
        session.pop(key, None)
    print(f"Failed to refresh token. Response: {response.text}")
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

def api_request(method, endpoint, api_version='v1', **kwargs):
    base_url = API_V2_BASE_URL if api_version == 'v2' else API_BASE_URL
    token = session.get(TOKEN_SESSION_KEY)
    headers = {'Authorization': f"Bearer {token}", 'Platform': 'open_platform', 'Content-Type': 'application/json'}
    try:
        response = requests.request(method, f"{base_url}{endpoint}", headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
        return None

# --- 核心路由 ---
@app.route('/', methods=['GET', 'POST'])
def configure():
    """显示配置页面并处理凭证提交。"""
    if request.method == 'POST':
        client_id = request.form.get('client_id')
        client_secret = request.form.get('client_secret')

        if not client_id or not client_secret:
            flash('Client ID 和 Client Secret 均不能为空。', 'error')
            return render_template('configure.html')
        
        session[CLIENT_ID_SESSION_KEY] = client_id
        session[CLIENT_SECRET_SESSION_KEY] = client_secret
        session[TASK_IDS_SESSION_KEY] = []
        
        if get_access_token():
            flash('凭证已保存并验证成功！', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('提供的凭证无效，请重新检查并提交。', 'error')
            return render_template('configure.html')
            
    if session.get(CLIENT_ID_SESSION_KEY):
        return redirect(url_for('dashboard'))

    return render_template('configure.html')

@app.route('/dashboard')
@credentials_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/add_tasks', methods=['POST'])
@credentials_required
def add_tasks():
    links_text = request.form.get('links')
    dir_id = request.form.get('dirID')
    links = [link.strip() for link in links_text.splitlines() if link.strip()]
    if not links:
        flash('下载链接不能为空。', 'error')
        return redirect(url_for('dashboard'))

    added_count = 0
    for link in links:
        payload = {'url': link}
        if dir_id and dir_id.isdigit():
            payload['dirID'] = int(dir_id)
        
        result = api_request('post', '/offline/download', json=payload)
        if result and result.get('code') == 0:
            task_id = result['data']['taskID']
            session.setdefault(TASK_IDS_SESSION_KEY, []).append(task_id)
            added_count += 1
    
    session.modified = True
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
        if last_file_id != 0:
            params['lastFileId'] = last_file_id
        
        list_data = api_request('get', '/file/list', api_version='v2', params=params)
        if not (list_data and list_data.get('code') == 0):
            return jsonify({"error": "Failed to fetch folders"}), 500

        data = list_data.get('data', {})
        file_list = data.get('fileList', [])
        
        for item in file_list:
            if item['type'] == 1 and item.get('trashed', 0) == 0:
                all_folders.append({"id": item['fileId'], "name": item['filename']})
        
        last_file_id = data.get('lastFileId', -1)
        if last_file_id == -1:
            break
    return jsonify(all_folders)

@app.route('/api/tasks_status')
@credentials_required
def get_tasks_status():
    task_ids = session.get(TASK_IDS_SESSION_KEY, [])
    if not task_ids: return jsonify({})
    status_map = {}
    for task_id in task_ids:
        progress_data = api_request('get', '/offline/download/process', params={'taskID': task_id})
        if progress_data and progress_data.get('code') == 0:
            status_map[task_id] = progress_data['data']
        else:
            status_map[task_id] = {'status': -1, 'process': 0}
    return jsonify(status_map)

@app.route('/logout')
def logout():
    session.clear()
    DIR_ID_CACHE.clear()
    flash('您已退出，所有凭证和任务列表已被清除。', 'info')
    return redirect(url_for('configure'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)