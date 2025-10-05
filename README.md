# 123Pan Self-Hosted Offline Dashboard

一个安全、开源、自托管的123云盘离线下载管理面板。

![Dashboard Screenshot](https://p.inari.site/usr/1764/68aab99e51720.jpg)

## ✨ 功能特性

- **🔒 安全**: 您的 `Client ID` 和 `Client Secret` 仅保存在您自己的服务器会话中，代码完全开源可审查，确保您的凭证无任何泄露风险。
- **🚀 批量添加**: 一次性粘贴多个下载链接，一键提交所有任务，告别繁琐的单条添加。
- **🌳 可视化目录选择**: 提供交互式文件夹浏览器，通过点击即可逐级选择保存位置，无需手动查找和输入数字ID。
- **📊 实时监控**: 仪表盘每3秒自动刷新，实时展示所有任务的下载状态和带百分比的进度条。
- **💪 稳定可靠**:
    - 使用官方最新的v2文件列表API，支持分页，能可靠地遍历大文件夹并过滤回收站内容。
    - 自动管理`access_token`，在其过期前自动刷新，保证服务持久稳定。
    - 内置路径ID缓存，重复选择目录时可实现秒级响应。
- **🌐 轻松部署**: 基于Python Flask，无复杂依赖，可在任何支持Python的环境（包括Termux、Docker、VPS）中快速运行。
- **👨‍💻 用户友好**: 无需修改任何代码或配置文件，直接在网页上完成所有凭证配置。

## 🔐 工作原理 (安全性)

本应用严格遵循123云盘官方的OpenAPI认证流程。您在网页上输入的开发者凭证**不会被存储在任何文件或数据库中**。它们仅被临时保存在您当前浏览器对应的服务器会话(Session)里，这是一个加密的、临时的服务器端存储。当您关闭浏览器或点击“退出”后，这些信息将被彻底清除。

## 🚀 如何运行 (本地/服务器部署)

**前提**: 您的设备上已安装 Python 3.7+ 和 pip。

### 1. 获取开发者凭证

您需要先从123云盘官方获取凭证：

1.  访问 [123云盘开放平台](https://www.123pan.cn/developer)。
2.  申请成为开发者。
3.  创建一个新应用，您将获得 `Client ID` 和 `Client Secret`。请妥善保管。

### 2. 部署应用

```bash
# 1. 克隆本项目
git clone https://github.com/ZZ0YY/123pan-offline-dashboard.git
cd 123pan-offline-dashboard

# 2. (推荐) 创建并激活Python虚拟环境
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux/Termux: source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 创建.env文件并配置密钥
# 您需要为Flask会话设置一个加密密钥。
# 复制模板文件
cp .env.example .env
# 然后用文本编辑器打开.env文件，将SECRET_KEY修改为一个长而随机的字符串

# 5. 启动应用
# 对于Termux或需要局域网访问的情况，请使用 --host=0.0.0.0
flask run --host=0.0.0.0