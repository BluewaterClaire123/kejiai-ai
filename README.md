# 客迹 AI

每个客户的AI记忆体 —— 一个帮助销售团队管理客户信息的 AI Agent。为每个客户建立持续记忆的会话：上传聊天截图、会议纪要、Word 文档等材料，Agent 自动提取关键业务信息并维护一份持续更新的客户档案卡，同时支持基于全部上下文的自然语言问答。

## 技术栈

- Python + Streamlit
- DeepSeek API（兼容 OpenAI SDK，模型 `deepseek-chat`）
- 合合信息 TextIn API（OCR + 文档解析）

## 本地运行

### 1. 安装依赖

建议使用虚拟环境：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置密钥

在项目根目录创建 `.streamlit/secrets.toml`（该文件已在 `.gitignore` 中排除，不会被提交）：

```toml
DEEPSEEK_API_KEY = "sk-xxx"
TEXTIN_APP_ID = "xxx"
TEXTIN_SECRET_CODE = "xxx"
```

- `DEEPSEEK_API_KEY`：DeepSeek 开放平台的 API Key，参见 https://platform.deepseek.com
- `TEXTIN_APP_ID` / `TEXTIN_SECRET_CODE`：合合信息 TextIn 开放平台的应用凭证，参见 https://www.textin.com

### 3. 启动应用

```bash
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。

## 使用方式

1. 在左侧侧边栏「➕ 新建客户」输入客户名称并回车，创建后自动切换为当前客户；侧边栏「📂 客户列表」可随时点击切换客户，每个客户的对话与档案完全独立
2. 在主区域上传与该客户相关的材料（截图 JPG/PNG、会议纪要 PDF、Word 文档 DOCX、纯文本 TXT），或点击「🎤 语音备忘」录一段语音备忘（自动转文字后按普通消息处理，适合见完客户后随手录一段口头总结）
3. Agent 会自动解析材料内容，提取核心需求、决策人、预算、时间线、已确认事项、待办与风险，并更新侧边栏的客户档案卡；新材料与已有信息冲突时会明确标注变更
4. 在下方对话框中用自然语言提问，或点击 Agent 回复下方的推荐追问按钮，Agent 会基于已积累的全部上下文回答
5. 如需清空当前客户的所有记忆，点击侧边栏「🗑️ 清空当前客户对话与档案」；删除某个客户则点击其列表条目旁的「🗑️」
6. 侧边栏底部「📥 加载演示数据」可一键载入一份预置的示例客户档案，用于快速演示

语音备忘功能依赖浏览器麦克风权限和 Google 语音识别的公共接口，仅在 `https://` 或 `http://localhost` 环境下可用；部署到 Streamlit Community Cloud 后天然是 HTTPS，无需额外配置。

## 部署到 Streamlit Community Cloud

1. 将本项目推送到一个 GitHub 仓库（`.streamlit/secrets.toml` 不会随 `.gitignore` 一起提交，属预期行为）
2. 登录 https://share.streamlit.io ，选择 "New app"，关联该仓库与分支，Main file path 填写 `app.py`
3. 在应用的 **Settings → Secrets** 中粘贴以下内容（与本地 `secrets.toml` 内容一致）：

   ```toml
   DEEPSEEK_API_KEY = "sk-xxx"
   TEXTIN_APP_ID = "xxx"
   TEXTIN_SECRET_CODE = "xxx"
   ```

4. 点击 "Deploy"，等待构建完成后即可通过分配的 `*.streamlit.app` 域名访问

## 目录结构

```
.
├── app.py                     # 主应用（全部业务逻辑）
├── requirements.txt           # Python 依赖
├── .streamlit/
│   ├── config.toml            # 主题配置（已提交）
│   └── secrets.toml           # 密钥配置（需自行创建，不提交）
├── .gitignore
└── README.md
```
