"""客迹AI - 客户信息管理 AI Agent (Streamlit 应用)"""

import json

import requests
import streamlit as st
from openai import OpenAI

# ============================================================
# 常量与配置
# ============================================================

SYSTEM_PROMPT = """你是"客迹AI"，一位专业的客户信息管理助手。你帮助销售团队理解和记忆客户沟通信息。

## 工作模式

### 当用户上传了新的客户沟通材料时：
1. 仔细阅读全部内容，提取关键业务信息
2. 将信息分类到六个维度：
   - 核心需求：客户要解决什么问题、想要什么能力
   - 决策人与关键联系人：谁拍板、谁对接、各自关注什么
   - 预算与商务条件：金额、付款方式、采购流程
   - 时间线与里程碑：关键节点、紧迫程度
   - 已确认事项：双方已达成共识的决定
   - 待办事项与风险：需跟进的事、风险信号
3. 以清晰格式汇报提取到的新信息
4. 如果新信息与已有信息冲突，明确标注变更（如"⚠️ 预算更新：由80万调整为50万"）
5. 不确定的信息标注"待确认"

### 当用户提问时：
- 基于所有已积累的信息回答，引用信息来源
- 信息不足时明确告知并建议补充什么
- 给建议时要具体、有针对性

### 当收到指令 [SYSTEM:UPDATE_PROFILE] 时：
仅输出以下JSON，不要有任何其他文字：
{"customer_name":"客户名","core_needs":["需求1","需求2"],"decision_makers":[{"name":"姓名","role":"角色"}],"budget":"预算描述","timeline":[{"date":"时间","event":"事件"}],"confirmed_items":["事项1"],"action_items":[{"item":"待办","priority":"高/中/低"}],"recent_updates":[{"date":"日期","summary":"摘要"}]}

## 沟通风格
- 专业简洁，信息密度高
- 主动发现风险和跟进机会
- 不确定的不编造
"""

SUPPORTED_EXTENSIONS = ["jpg", "jpeg", "png", "pdf", "docx", "txt"]

SUGGESTED_QUESTIONS = [
    "这个客户目前最大的风险是什么？",
    "帮我准备下次会议要点",
    "还有哪些信息需要补充？",
]

MAX_MESSAGES = 40
KEEP_RECENT_MESSAGES = 30


# ============================================================
# 客户端初始化
# ============================================================

def get_deepseek_client() -> OpenAI:
    return OpenAI(
        api_key=st.secrets["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )


# ============================================================
# TextIn API
# ============================================================

def parse_with_textin(file_bytes: bytes, app_id: str, secret_code: str) -> str:
    """
    调用合合信息 TextIn API 解析文档/图片
    返回解析后的 Markdown 文本
    """
    url = "https://api.textin.com/ai/service/v1/pdf_to_markdown"
    headers = {
        "x-ti-app-id": app_id,
        "x-ti-secret-code": secret_code,
        "Content-Type": "application/octet-stream",
    }
    params = {
        "markdown_details": 1,
        "parse_mode": "auto",
    }

    response = requests.post(
        url, headers=headers, params=params, data=file_bytes, timeout=120
    )

    if response.status_code != 200:
        raise Exception(f"TextIn API HTTP错误: {response.status_code}")

    result = response.json()
    if result.get("code") != 200:
        raise Exception(f"TextIn API返回错误: {result.get('message', '未知错误')}")

    return result["result"]["markdown"]


# ============================================================
# 对话历史裁剪
# ============================================================

def trim_messages(messages, max_len=MAX_MESSAGES, keep_recent=KEEP_RECENT_MESSAGES):
    if len(messages) <= max_len:
        return messages

    system = messages[0]
    old = messages[1:-keep_recent]
    recent = messages[-keep_recent:]

    if not old:
        return messages

    try:
        client = get_deepseek_client()
        old_text = "\n".join(
            [m.get("content", "") for m in old if isinstance(m.get("content"), str)]
        )
        summary_resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "user",
                    "content": "请用3-5句话总结以下对话中关于客户的关键信息，只保留事实：\n\n"
                    + old_text,
                }
            ],
            temperature=0.1,
            stream=False,
        )
        summary = summary_resp.choices[0].message.content
    except Exception:
        summary = "（历史摘要生成失败，已省略更早的对话内容）"

    return (
        [system, {"role": "system", "content": f"[之前的对话摘要] {summary}"}]
        + recent
    )


# ============================================================
# 客户档案静默更新
# ============================================================

def update_profile_silently(customer_data):
    """静默调用模型获取最新客户档案JSON，用户不可见"""
    try:
        client = get_deepseek_client()
        profile_messages = customer_data["messages"].copy()
        profile_messages.append(
            {"role": "user", "content": "[SYSTEM:UPDATE_PROFILE]"}
        )

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=profile_messages,
            temperature=0.1,
            stream=False,
        )

        content = response.choices[0].message.content.strip()

        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        try:
            profile = json.loads(content)
            customer_data["profile"] = profile
        except json.JSONDecodeError:
            pass  # 解析失败保持旧档案
    except Exception:
        pass  # 更新失败静默忽略，不影响主对话


# ============================================================
# 侧边栏 - 客户档案卡渲染
# ============================================================

def render_profile(profile):
    """在侧边栏渲染客户档案卡"""
    if not profile:
        st.sidebar.caption("上传客户材料后，档案将自动生成")
        return

    st.sidebar.markdown(f"### 📇 {profile.get('customer_name') or '未命名客户'}")
    st.sidebar.divider()

    needs = profile.get("core_needs") or []
    if needs:
        st.sidebar.markdown("**📋 核心需求**")
        for n in needs:
            st.sidebar.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• {n}")
        st.sidebar.markdown("")

    makers = profile.get("decision_makers") or []
    if makers:
        st.sidebar.markdown("**👤 决策人**")
        for m in makers:
            name = m.get("name", "") if isinstance(m, dict) else str(m)
            role = m.get("role", "") if isinstance(m, dict) else ""
            if role:
                st.sidebar.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• **{name}**（{role}）")
            else:
                st.sidebar.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• {name}")
        st.sidebar.markdown("")

    budget = profile.get("budget") or ""
    if budget:
        st.sidebar.markdown("**💰 预算与商务**")
        st.sidebar.info(budget)

    timeline = profile.get("timeline") or []
    if timeline:
        st.sidebar.markdown("**📅 时间线**")
        for t in timeline:
            if isinstance(t, dict):
                st.sidebar.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;📌 {t.get('date', '')}: {t.get('event', '')}")
            else:
                st.sidebar.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;📌 {t}")
        st.sidebar.markdown("")

    confirmed = profile.get("confirmed_items") or []
    if confirmed:
        st.sidebar.markdown("**✅ 已确认事项**")
        for c in confirmed:
            st.sidebar.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• {c}")
        st.sidebar.markdown("")

    actions = profile.get("action_items") or []
    if actions:
        st.sidebar.markdown("**⚠️ 待办与风险**")
        for a in actions:
            if isinstance(a, dict):
                priority = a.get("priority", "")
                item_text = a.get("item", "")
                if "高" in str(priority):
                    st.sidebar.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;🔴 **{item_text}**（{priority}）")
                elif "中" in str(priority):
                    st.sidebar.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;🟡 {item_text}（{priority}）")
                else:
                    st.sidebar.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;🟢 {item_text}（{priority}）")
            else:
                st.sidebar.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• {a}")
        st.sidebar.markdown("")

    updates = profile.get("recent_updates") or []
    if updates:
        st.sidebar.markdown("**📝 最近更新**")
        for u in updates[-3:]:
            if isinstance(u, dict):
                st.sidebar.caption(f"[{u.get('date', '')}] {u.get('summary', '')}")
            else:
                st.sidebar.caption(str(u))


# ============================================================
# session_state 初始化（多客户结构）
# ============================================================

def init_session_state():
    if "customers" not in st.session_state:
        st.session_state.customers = {}  # {客户名: {"messages", "profile", "chat_display", "processed_file_keys"}}
    if "current_customer" not in st.session_state:
        st.session_state.current_customer = ""


def get_customer_data(name):
    """获取或初始化指定客户的数据"""
    if not name:
        return None
    if name not in st.session_state.customers:
        st.session_state.customers[name] = {
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
            "profile": None,
            "chat_display": [],  # 仅用于界面展示，不进入模型上下文
            "processed_file_keys": set(),
        }
    return st.session_state.customers[name]


# ============================================================
# 核心业务逻辑：处理上传的文件
# ============================================================

def handle_uploaded_files(customer_data, uploaded_files, app_id, secret_code):
    processed_any = False
    for uploaded_file in uploaded_files:
        file_key = f"{uploaded_file.name}-{uploaded_file.size}"
        if file_key in customer_data["processed_file_keys"]:
            continue
        customer_data["processed_file_keys"].add(file_key)
        processed_any = True

        ext = uploaded_file.name.split(".")[-1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            with st.chat_message("assistant"):
                st.warning("目前支持 JPG/PNG/PDF/DOCX/TXT 格式")
            customer_data["chat_display"].append(
                {
                    "role": "assistant",
                    "content": "目前支持 JPG/PNG/PDF/DOCX/TXT 格式",
                }
            )
            continue

        file_bytes = uploaded_file.read()
        if not file_bytes:
            with st.chat_message("assistant"):
                st.warning("文件内容为空，请检查后重新上传")
            customer_data["chat_display"].append(
                {
                    "role": "assistant",
                    "content": "文件内容为空，请检查后重新上传",
                }
            )
            continue

        user_display_msg = f"📎 上传了文件：{uploaded_file.name}"
        customer_data["chat_display"].append(
            {"role": "user", "content": user_display_msg}
        )
        with st.chat_message("user"):
            st.markdown(user_display_msg)

        # 纯文本文件直接读取，无需调用 TextIn
        if ext == "txt":
            try:
                markdown_text = file_bytes.decode("utf-8", errors="ignore")
            except Exception:
                markdown_text = ""
        else:
            with st.chat_message("assistant"):
                with st.spinner(f"正在解析文档 {uploaded_file.name} ..."):
                    try:
                        markdown_text = parse_with_textin(
                            file_bytes, app_id, secret_code
                        )
                    except Exception:
                        st.error("文档解析暂时不可用，请稍后重试")
                        customer_data["chat_display"].append(
                            {
                                "role": "assistant",
                                "content": "文档解析暂时不可用，请稍后重试",
                            }
                        )
                        continue

        if not markdown_text or not markdown_text.strip():
            with st.chat_message("assistant"):
                st.warning("文件内容为空，请检查后重新上传")
            customer_data["chat_display"].append(
                {
                    "role": "assistant",
                    "content": "文件内容为空，请检查后重新上传",
                }
            )
            continue

        user_message = (
            f"我上传了一份客户材料：{uploaded_file.name}\n\n"
            f"以下是解析出的内容：\n{markdown_text}"
        )
        customer_data["messages"].append({"role": "user", "content": user_message})

        run_assistant_turn(customer_data)

    return processed_any


def run_assistant_turn(customer_data):
    """调用 DeepSeek 完成一轮助手回复（流式），并静默更新客户档案"""
    customer_data["messages"] = trim_messages(customer_data["messages"])

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("正在思考...")
        full_response = ""
        try:
            client = get_deepseek_client()
            stream = client.chat.completions.create(
                model="deepseek-chat",
                messages=customer_data["messages"],
                temperature=0.3,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_response += delta
                    placeholder.markdown(full_response + "▌")
            placeholder.markdown(full_response)
        except Exception:
            full_response = "抱歉，AI 服务暂时不可用，请稍后重试。"
            placeholder.error(full_response)

    customer_data["messages"].append(
        {"role": "assistant", "content": full_response}
    )
    customer_data["chat_display"].append(
        {"role": "assistant", "content": full_response}
    )

    update_profile_silently(customer_data)


# ============================================================
# 推荐追问
# ============================================================

def render_suggested_questions(customer_data):
    """在最新一条 Agent 回复下方展示可点击的推荐追问"""
    if not customer_data.get("profile"):
        return
    if not customer_data["chat_display"]:
        return
    if customer_data["chat_display"][-1]["role"] != "assistant":
        return

    st.markdown("---")
    st.caption("💡 你可以继续问我：")
    cols = st.columns(len(SUGGESTED_QUESTIONS))
    for i, suggestion in enumerate(SUGGESTED_QUESTIONS):
        with cols[i]:
            if st.button(
                suggestion,
                key=f"suggest_{len(customer_data['messages'])}_{i}",
                use_container_width=True,
            ):
                customer_data["chat_display"].append(
                    {"role": "user", "content": suggestion}
                )
                customer_data["messages"].append(
                    {"role": "user", "content": suggestion}
                )
                run_assistant_turn(customer_data)
                st.rerun()


# ============================================================
# 演示数据（用于快速展示效果）
# ============================================================

def load_demo_customer():
    """预置一个"演示客户-华为云"，供演示或 API 不可用时快速展示效果"""
    demo_name = "演示客户-华为云"
    demo_file_name = "华为云项目会议纪要.pdf"
    demo_material = (
        "# 华为云智能文档处理平台项目 - 第二轮需求沟通会议纪要\n\n"
        "**日期**：2026年8月25日\n"
        "**参会人**：张明远（华为云产品总监）、李薇（采购负责人）、王建国（IT部门主管）\n\n"
        "## 核心需求\n"
        "- 需要一套智能文档处理平台，支持合同、发票、报告等多类型文档的自动识别和结构化提取\n"
        "- 日均处理量预计5000-8000份文档\n"
        "- 需要与现有OA系统对接\n\n"
        "## 预算\n"
        "- 初步预算100万/年，含平台授权+技术支持\n"
        "- 李薇提到如果一期效果好，二期预算可以追加到200万\n\n"
        "## 时间线\n"
        "- 9月中旬前需要完成POC验证\n"
        "- 10月底前完成一期上线\n"
        "- 张明远强调：集团年底有数字化考核指标，时间比较紧\n\n"
        "## 待确认事项\n"
        "- IT部门需要评估API并发能力\n"
        "- 安全合规审查流程大约需要2-3周"
    )
    demo_reply = (
        "收到华为云项目的会议纪要，我已提取以下关键信息：\n\n"
        "**📋 核心需求**\n"
        "- 智能文档处理平台：支持合同、发票、报告等多类型文档自动识别和结构化提取\n"
        "- 日均处理量：5000-8000份\n"
        "- 系统集成：需要与现有OA系统对接\n\n"
        "**👤 决策人与关键联系人**\n"
        "- **张明远**（产品总监）：核心决策人，关注时间进度，有年底数字化考核压力\n"
        "- **李薇**（采购负责人）：管预算，对效果有信心则愿追加\n"
        "- **王建国**（IT部门主管）：技术把关，需评估API并发能力\n\n"
        "**💰 预算**\n"
        "- 一期：100万/年（含平台授权+技术支持）\n"
        "- 二期：可追加至200万（取决于一期效果）\n\n"
        "**📅 关键时间节点**\n"
        "- 9月中旬：完成POC验证\n"
        "- 10月底：一期上线\n"
        "- ⚠️ 年底前有集团数字化考核指标，时间紧迫\n\n"
        "**⚠️ 待办与风险**\n"
        "- 🔴 IT部门API并发能力评估（影响技术方案）\n"
        "- 🟡 安全合规审查（预计2-3周，可能影响时间线）\n"
        "- 🔴 9月中旬POC验证时间紧，距今不到3周"
    )

    st.session_state.customers[demo_name] = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"我上传了一份客户材料：{demo_file_name}\n\n以下是解析出的内容：\n{demo_material}",
            },
            {"role": "assistant", "content": demo_reply},
        ],
        "profile": {
            "customer_name": "华为云",
            "core_needs": [
                "智能文档处理平台，支持合同/发票/报告等多类型文档自动识别与结构化提取",
                "日均处理量5000-8000份文档",
                "与现有OA系统对接",
            ],
            "decision_makers": [
                {"name": "张明远", "role": "产品总监，核心决策人"},
                {"name": "李薇", "role": "采购负责人"},
                {"name": "王建国", "role": "IT部门主管，技术把关"},
            ],
            "budget": "一期100万/年（含授权+技术支持），二期可追加至200万",
            "timeline": [
                {"date": "2026年9月中旬", "event": "完成POC验证"},
                {"date": "2026年10月底", "event": "一期上线"},
                {"date": "2026年底", "event": "集团数字化考核节点"},
            ],
            "confirmed_items": [
                "文档类型范围：合同、发票、报告",
                "对接方式：API集成到现有OA系统",
            ],
            "action_items": [
                {"item": "POC验证方案准备（距9月中旬不到3周）", "priority": "高"},
                {"item": "IT部门API并发能力评估", "priority": "高"},
                {"item": "安全合规审查启动（预计2-3周）", "priority": "中"},
            ],
            "recent_updates": [
                {"date": "2026-08-25", "summary": "第二轮需求沟通完成，明确预算100万/年，时间节点9月中旬POC"},
            ],
        },
        "chat_display": [
            {"role": "user", "content": f"📎 上传了文件：{demo_file_name}"},
            {"role": "assistant", "content": demo_reply},
        ],
        "processed_file_keys": set(),
    }
    st.session_state.current_customer = demo_name


# ============================================================
# 主程序
# ============================================================

def main():
    st.set_page_config(page_title="客迹AI", page_icon="🔍", layout="wide")
    init_session_state()

    # ---------------- 侧边栏 ----------------
    with st.sidebar:
        st.title("🔍 客迹 AI")
        st.caption("每个客户的AI记忆体")

        # 新建客户
        if "new_customer_key_version" not in st.session_state:
            st.session_state.new_customer_key_version = 0
        new_customer = st.text_input(
            "➕ 新建客户",
            placeholder="输入客户名称，回车创建",
            key=f"new_customer_input_{st.session_state.new_customer_key_version}",
        )
        if new_customer and new_customer not in st.session_state.customers:
            get_customer_data(new_customer)
            st.session_state.current_customer = new_customer
            # 换一个新 key，强制输入框在下一次渲染时清空
            # 否则残留的文本在删除该客户后会被这段逻辑当作"新客户"重新创建出来
            st.session_state.new_customer_key_version += 1
            st.rerun()

        st.divider()

        # 客户列表（可点击切换）
        if st.session_state.customers:
            st.markdown("**📂 客户列表**")
            for name in list(st.session_state.customers.keys()):
                col1, col2 = st.columns([4, 1])
                with col1:
                    label = f"{'👉 ' if name == st.session_state.current_customer else ''}{name}"
                    if st.button(label, key=f"select_{name}", use_container_width=True):
                        st.session_state.current_customer = name
                        st.rerun()
                with col2:
                    if st.button("🗑️", key=f"delete_{name}"):
                        del st.session_state.customers[name]
                        if st.session_state.current_customer == name:
                            st.session_state.current_customer = ""
                        st.rerun()
        else:
            st.caption("还没有客户，先在上方新建一个吧")

        st.divider()

        # 当前客户的档案卡
        current_customer_data = get_customer_data(st.session_state.current_customer)
        if current_customer_data is not None:
            render_profile(current_customer_data["profile"])
            st.divider()
            if st.button("🗑️ 清空当前客户对话与档案", use_container_width=True):
                name = st.session_state.current_customer
                st.session_state.customers[name] = {
                    "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
                    "profile": None,
                    "chat_display": [],
                    "processed_file_keys": set(),
                }
                st.rerun()
        else:
            st.caption("上传客户材料后，档案将自动生成")

        st.divider()
        if st.button("📥 加载演示数据", use_container_width=True):
            load_demo_customer()
            st.rerun()

    # ---------------- 主区域 ----------------
    if not st.session_state.current_customer:
        st.markdown("### 👋 欢迎使用客迹 AI")
        st.info(
            "**三步开始使用：**\n\n"
            "1️⃣ 在左侧输入客户名称，创建客户\n\n"
            "2️⃣ 上传客户沟通材料（截图、PDF、Word等）\n\n"
            "3️⃣ AI 自动分析并建立客户档案，你可以随时提问"
        )
        return

    customer_data = current_customer_data
    st.markdown(f"### 💬 {st.session_state.current_customer}")

    # 首次进入该客户时显示欢迎语
    # 用 chat_display 是否为空判断，而不是 messages 长度：
    # 上传不支持格式/空文件时只会写入 chat_display（不会调用模型追加 messages），
    # 若按 messages 长度判断，这类中文提示会被下面的欢迎语覆盖、用户看不到
    if not customer_data["chat_display"]:
        with st.chat_message("assistant"):
            st.markdown(
                f"我是 **{st.session_state.current_customer}** 的专属记忆体 🧠\n\n"
                f"上传这位客户的沟通材料（微信截图、会议纪要、需求文档等），"
                f"我会自动提取关键信息并建立客户档案。\n\n"
                f"你也可以直接问我关于这位客户的任何问题。"
            )
    else:
        for msg in customer_data["chat_display"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        render_suggested_questions(customer_data)

    st.caption("支持 JPG/PNG/PDF/DOCX/TXT 格式，可多选")
    uploaded_files = st.file_uploader(
        "📎 上传客户材料",
        # 不通过 type= 限制格式：Streamlit 组件自身对不支持类型的拦截提示是英文且无法定制，
        # 交给下面 handle_uploaded_files() 里的中文提示统一处理，保证界面全中文
        accept_multiple_files=True,
        key=f"file_uploader_{st.session_state.current_customer}",
    )

    app_id = st.secrets.get("TEXTIN_APP_ID", "")
    secret_code = st.secrets.get("TEXTIN_SECRET_CODE", "")

    if uploaded_files:
        processed_any = handle_uploaded_files(
            customer_data, uploaded_files, app_id, secret_code
        )
        if processed_any:
            # 重新运行一次，让侧边栏用上刚刚静默更新出的最新客户档案
            st.rerun()

    user_input = st.chat_input("输入消息...")
    if user_input:
        customer_data["chat_display"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        customer_data["messages"].append({"role": "user", "content": user_input})
        run_assistant_turn(customer_data)
        # 重新运行一次，让侧边栏用上刚刚静默更新出的最新客户档案
        st.rerun()


if __name__ == "__main__":
    main()
