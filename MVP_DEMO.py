import streamlit as st
import streamlit_authenticator as stauth
from supabase import create_client, Client
from datetime import datetime, time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Any
import json
import schedule
import threading
import time as time_module
import numpy as np
import hashlib
import yaml
from yaml.loader import SafeLoader
# from dotenv import load_dotenv
import os
from openai import OpenAI

# load_dotenv()
# Initialize OpenAI client
QWEN_API_KEY = st.secrets["QWEN_API_KEY"]
openai_client = OpenAI(api_key=QWEN_API_KEY,
                       base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
# 配置
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = ost.secrets["SUPABASE_KEY"]

# 初始化客户端
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 页面配置
st.set_page_config(
    page_title="智慧人生规划系统",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)


def safe_rerun():
    """Call Streamlit rerun safely across versions."""
    try:
        # some streamlit versions expose experimental_rerun
        rerun = getattr(st, 'experimental_rerun', None)
        if callable(rerun):
            rerun()
        else:
            # fallback: set a flag and stop, next interaction will refresh
            st.session_state['_need_rerun'] = True
            st.stop()
    except Exception:
        # worst case: stop execution to force UI update
        st.session_state['_need_rerun'] = True
        st.stop()

# 自定义CSS
st.markdown("""
<style>
    .main {
        padding: 0rem 1rem;
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        border-radius: 10px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: bold;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #45a049;
        transform: translateY(-2px);
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 1rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    .info-card {
        background: white;
        padding: 1.5rem;
        border-radius: 15px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        margin-bottom: 1rem;
        border-left: 4px solid #4CAF50;
    }
</style>
""", unsafe_allow_html=True)

# 数据库初始化
def init_database():
    """初始化数据库表"""
    try:
        # 用户表
        supabase.table('users').select("*").limit(1).execute()
    except:
        pass
    
    try:
        # 用户数据表
        supabase.table('user_data').select("*").limit(1).execute()
    except:
        pass
    
    try:
        # 每日更新表
        supabase.table('daily_updates').select("*").limit(1).execute()
    except:
        pass

# 用户认证
def authenticate_user():
    """用户登录认证（使用 streamlit_authenticator）"""
    if 'authentication_status' not in st.session_state:
        st.session_state['authentication_status'] = None
    if 'username' not in st.session_state:
        st.session_state['username'] = None

    # Build credentials dict from Supabase users table
    try:
        users_res = supabase.table('users').select('id,username,email,password').execute()
        users = users_res.data or []
    except Exception:
        users = []

    credentials = {'users': {}}
    # password in DB is stored as sha256; streamlit_authenticator expects hashed passwords via its Hasher.
    # We'll allow direct check by falling back to custom authenticate_login when needed.
    for u in users:
        credentials['users'][u['username']] = {
            'email': u.get('email', ''),
            'name': u.get('username', ''),
            # Put placeholder for password; stauth requires a password but we'll authenticate separately
            'password': u.get('password', '')
        }

    with st.sidebar:
        st.title("🎯 智慧人生规划系统")
        if st.session_state['authentication_status'] is None:
            tab1, tab2 = st.tabs(["登录", "注册"])

            with tab1:
                with st.form("login_form"):
                    username = st.text_input("用户名")
                    password = st.text_input("密码", type="password")
                    login_button = st.form_submit_button("登录")

                    if login_button:
                        user = authenticate_login(username, password)
                        if user:
                            st.session_state['authentication_status'] = True
                            st.session_state['username'] = username
                            st.session_state['user_id'] = user['id']
                            safe_rerun()
                        else:
                            st.error("用户名或密码错误")

            with tab2:
                with st.form("register_form"):
                    new_username = st.text_input("用户名")
                    new_email = st.text_input("邮箱")
                    new_password = st.text_input("密码", type="password")
                    confirm_password = st.text_input("确认密码", type="password")
                    register_button = st.form_submit_button("注册")

                    if register_button:
                                if new_password != confirm_password:
                                    st.error("两次密码输入不一致")
                                else:
                                    if register_user(new_username, new_email, new_password):
                                        st.success("注册成功！请登录")
                                    else:
                                        st.error("注册失败，用户名可能已存在")

        elif st.session_state['authentication_status']:
            st.write(f"👤 欢迎, {st.session_state['username']}")
            if st.button("登出"):
                st.session_state['authentication_status'] = None
                st.session_state['username'] = None
                st.session_state['user_id'] = None
                safe_rerun()

def authenticate_login(username, password):
    """验证登录"""
    try:
        # Compare sha256 hashes stored in DB
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        result = supabase.table('users').select("*").eq('username', username).execute()
        if result.data and result.data[0].get('password') == hashed_pw:
            return result.data[0]
        return None
    except:
        return None

def register_user(username, email, password):
    """注册新用户"""
    try:
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        # basic uniqueness check
        existing = supabase.table('users').select('id').eq('username', username).execute()
        if existing.data:
            return False
        supabase.table('users').insert({
            'username': username,
            'email': email,
            'password': hashed_pw,
            'created_at': datetime.now().isoformat()
        }).execute()
        return True
    except:
        return False

# OpenAI API调用
def get_ai_suggestion(context: str, data_type: str) -> str:
    """获取AI建议"""
    try:
        # Structured JSON prompt to force consistent, professional output
        base_system = (
            "你是一位资深的职业顾问和分析师，面向中高净值用户。请基于用户给出的上下文，生成结构化的JSON输出，"
            "包含以下字段：summary(一句话总结), recommendations(要点列表), actions(可执行步骤列表), risks(潜在风险列表), confidence(可信度，0-100)。"
            "返回必须是有效JSON，不包含其他无关文本。每个列表项为字符串。"
        )

        user_prompt = (
            f"数据类型：{data_type}\n用户上下文：\n{context}\n\n请以JSON格式返回结果，保持字段完整且简洁。"
        )

        response = openai_client.chat.completions.create(
            model="qwen-plus-2025-09-11",
            messages=[
                {"role": "system", "content": base_system},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=500,
            temperature=0.2
        )

        # Parse response content
        content = None
        if getattr(response, 'choices', None):
            c = response.choices[0]
            if hasattr(c, 'message') and hasattr(c.message, 'content'):
                content = c.message.content
            else:
                content = str(c)
        else:
            content = str(response)

        # Try to extract JSON from content
        try:
            # If the model returned code block or text, attempt to find first '{'
            text = str(content)
            json_start = text.find('{')
            if json_start != -1:
                json_text = text[json_start:]
            else:
                json_text = text
            parsed = json.loads(json_text)
            # Format into a readable string
            out_lines = []
            out_lines.append(parsed.get('summary', ''))
            if parsed.get('recommendations'):
                out_lines.append('\n推荐要点:')
                for r in parsed.get('recommendations'):
                    out_lines.append(f"- {r}")
            if parsed.get('actions'):
                out_lines.append('\n可执行步骤:')
                for a in parsed.get('actions'):
                    out_lines.append(f"- {a}")
            if parsed.get('risks'):
                out_lines.append('\n潜在风险:')
                for rk in parsed.get('risks'):
                    out_lines.append(f"- {rk}")
            conf = parsed.get('confidence')
            if conf is not None:
                out_lines.append(f"\n可信度: {conf}%")
            return "\n".join([l for l in out_lines if l])
        except Exception:
            # Fallback to raw content
            return str(content)
    except Exception as e:
        return f"建议生成中遇到问题，请稍后再试。错误：{str(e)}"


def get_cached_ai_suggestion(user_id: str, context: str, data_type: str) -> str:
    """Return cached AI suggestion per user per day; update at most once per day."""
    try:
        if not user_id:
            return get_ai_suggestion(context, data_type)

        field_text = f"ai_{data_type}_suggestion"
        field_date = f"last_ai_{data_type}_date"

        user_row = supabase.table('user_data').select('*').eq('user_id', user_id).execute()
        existing = (user_row.data[0] if user_row.data else {})

        today = datetime.now().date().isoformat()
        if existing.get(field_text) and existing.get(field_date) == today:
            return str(existing.get(field_text) or "")

        # generate new suggestion and save
        suggestion = get_ai_suggestion(context, data_type)
        update = {field_text: suggestion, field_date: today, 'updated_at': datetime.now().isoformat()}
        if existing:
            supabase.table('user_data').update(update).eq('user_id', user_id).execute()
        else:
            update['user_id'] = user_id
            update['created_at'] = datetime.now().isoformat()
            supabase.table('user_data').insert(update).execute()

        return suggestion
    except Exception:
        return get_ai_suggestion(context, data_type)

def get_daily_updates():
    """获取每日更新的资讯"""
    try:
        today = datetime.now().date().isoformat()
        # If today's updates already exist, return them
        existing = supabase.table('daily_updates').select('*').eq('date', today).execute()
        if existing.data:
            row = existing.data[0]
            return {
                'finance': row.get('finance_news', ''),
                'health': row.get('health_tips', ''),
                'education': row.get('education_info', '')
            }

        updates = {}

        # 获取金融新闻
        finance_prompt = "请提供今日3条最重要的全球金融市场动态，每条不超过50字。"
        finance_response = openai_client.chat.completions.create(
            model="qwen-plus-2025-09-11",
            messages=[{"role": "user", "content": finance_prompt}],
            max_tokens=200
        )
        if getattr(finance_response, 'choices', None):
            c = finance_response.choices[0]
            if hasattr(c, 'message') and hasattr(c.message, 'content'):
                updates['finance'] = str(c.message.content or "")
            else:
                updates['finance'] = str(c)
        else:
            updates['finance'] = str(finance_response)

        # 获取健康知识
        health_prompt = "请提供一条实用的健康小贴士，不超过100字。"
        health_response = openai_client.chat.completions.create(
            model="qwen-plus-2025-09-11",
            messages=[{"role": "user", "content": health_prompt}],
            max_tokens=150
        )
        if getattr(health_response, 'choices', None):
            c = health_response.choices[0]
            if hasattr(c, 'message') and hasattr(c.message, 'content'):
                updates['health'] = str(c.message.content or "")
            else:
                updates['health'] = str(c)
        else:
            updates['health'] = str(health_response)

        # 获取教育资讯
        edu_prompt = "请提供一条关于K12教育或高等教育的最新资讯或建议，不超过100字。"
        edu_response = openai_client.chat.completions.create(
            model="qwen-plus-2025-09-11",
            messages=[{"role": "user", "content": edu_prompt}],
            max_tokens=150
        )
        if getattr(edu_response, 'choices', None):
            c = edu_response.choices[0]
            if hasattr(c, 'message') and hasattr(c.message, 'content'):
                updates['education'] = str(c.message.content or "")
            else:
                updates['education'] = str(c)
        else:
            updates['education'] = str(edu_response)

        # 保存到数据库（仅当无今日记录）
        supabase.table('daily_updates').insert({
            'date': today,
            'finance_news': updates['finance'],
            'health_tips': updates['health'],
            'education_info': updates['education'],
            'created_at': datetime.now().isoformat()
        }).execute()

        return updates
    except Exception as e:
        st.error(f"获取每日更新失败：{str(e)}")
        return None

# 数据管理
def save_user_data(user_id: str, data: Dict[str, Any]):
    """保存用户数据"""
    try:
        # 检查是否已有数据
        existing = supabase.table('user_data').select("*").eq('user_id', user_id).execute()
        
        data['user_id'] = user_id
        data['updated_at'] = datetime.now().isoformat()
        
        if existing.data:
            # 更新现有数据
            result = supabase.table('user_data').update(data).eq('user_id', user_id).execute()
        else:
            # 插入新数据
            data['created_at'] = datetime.now().isoformat()
            result = supabase.table('user_data').insert(data).execute()
        
        return True
    except Exception as e:
        st.error(f"保存数据失败：{str(e)}")
        return False

def load_user_data(user_id: str) -> Dict[str, Any]:
    """加载用户数据"""
    try:
        result = supabase.table('user_data').select("*").eq('user_id', user_id).execute()
        if result.data:
            return result.data[0]
        return {}
    except:
        return {}

def load_daily_updates() -> Dict[str, Any]:
    """加载今日更新"""
    try:
        today = datetime.now().date().isoformat()
        result = supabase.table('daily_updates').select("*").eq('date', today).execute()
        if result.data:
            return result.data[0]
        else:
            # 如果今天没有更新，立即获取
            updates = get_daily_updates()
            return updates or {}
    except:
        return {}


def _scheduled_fetch_daily_updates():
    """内部函数：每天定时抓取并保存每日更新"""
    try:
        get_daily_updates()
    except Exception as e:
        # swallow errors in scheduler
        print("Scheduled update failed:", e)


def start_scheduler_in_background():
    """Start schedule loop in a background thread once per session"""
    if st.session_state.get('_scheduler_started'):
        return

    def run_loop():
        # schedule job at 07:00 daily
        schedule.clear('daily_updates')
        schedule.every().day.at("07:00").do(_scheduled_fetch_daily_updates).tag('daily_updates')
        while True:
            try:
                schedule.run_pending()
            except Exception as e:
                print('Scheduler error', e)
            time_module.sleep(60)

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    st.session_state['_scheduler_started'] = True

# 页面功能
def dashboard_page():
    """主页面"""
    st.title("📊 智能仪表盘")
    
    user_data = load_user_data(st.session_state.get('user_id', ''))
    daily_updates = load_daily_updates()
    
    # 概览指标
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_assets = user_data.get('total_assets', 0)
        st.metric("总资产", f"¥{total_assets:,.0f}", "↑ 5.2%")
    
    with col2:
        health_score = user_data.get('health_score', 85)
        st.metric("健康评分", f"{health_score}/100", "↑ 2")
    
    with col3:
        edu_progress = user_data.get('education_progress', 75)
        st.metric("教育进度", f"{edu_progress}%", "→")
    
    with col4:
        life_score = user_data.get('life_score', 88)
        st.metric("人生规划评分", f"{life_score}/100", "↑ 3")
    
    st.markdown("---")
    
    # AI综合建议
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("🤖 AI综合建议")

        context = f"""
        用户资产：{user_data.get('total_assets', 0)}万元
        健康状况：{user_data.get('health_status', '良好')}
        教育目标：{user_data.get('education_goals', '未设定')}
        人生阶段：{user_data.get('life_stage', '事业发展期')}
        """

        suggestion = get_cached_ai_suggestion(st.session_state.get('user_id', ''), context, 'life')
        st.info(suggestion)
        
        # 可视化图表
        st.subheader("📈 资产配置分布")
        
        allocation_data = {
            '股票': user_data.get('stock_percentage', 30),
            '债券': user_data.get('bond_percentage', 20),
            '房产': user_data.get('property_percentage', 35),
            '现金': user_data.get('cash_percentage', 15)
        }
        
        fig = px.pie(
            values=list(allocation_data.values()),
            names=list(allocation_data.keys()),
            color_discrete_sequence=['#FF6B6B', '#4ECDC4', '#45B7D1', '#96E6B3']
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("📰 今日资讯")
        
        if daily_updates:
            st.markdown("**金融动态**")
            st.write(daily_updates.get('finance_news', '暂无更新'))
            
            st.markdown("**健康贴士**")
            st.write(daily_updates.get('health_tips', '暂无更新'))
            
            st.markdown("**教育资讯**")
            st.write(daily_updates.get('education_info', '暂无更新'))
        else:
            st.info("正在获取今日资讯...")

def investment_page():
    """投资页面"""
    st.title("💰 投资管理")
    
    user_data = load_user_data(st.session_state.get('user_id', ''))
    daily_updates = load_daily_updates()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("资产配置")
        
        # 资产配置表单
        with st.form("asset_form"):
            total_assets = st.number_input("总资产（万元）", value=user_data.get('total_assets', 0), min_value=0)
            
            col_a, col_b = st.columns(2)
            with col_a:
                stock_pct = st.slider("股票占比(%)", 0, 100, user_data.get('stock_percentage', 30))
                bond_pct = st.slider("债券占比(%)", 0, 100, user_data.get('bond_percentage', 20))
            
            with col_b:
                property_pct = st.slider("房产占比(%)", 0, 100, user_data.get('property_percentage', 35))
                cash_pct = st.slider("现金占比(%)", 0, 100, user_data.get('cash_percentage', 15))
            
            risk_level = st.select_slider(
                "风险偏好",
                options=['保守', '稳健', '平衡', '进取', '激进'],
                value=user_data.get('risk_level', '平衡')
            )
            
            if st.form_submit_button("保存配置"):
                if stock_pct + bond_pct + property_pct + cash_pct != 100:
                    st.error("资产配置比例总和必须等于100%")
                else:
                    data = {
                        'total_assets': total_assets,
                        'stock_percentage': stock_pct,
                        'bond_percentage': bond_pct,
                        'property_percentage': property_pct,
                        'cash_percentage': cash_pct,
                        'risk_level': risk_level
                    }
                    if save_user_data(st.session_state['user_id'], data):
                        st.success("资产配置已更新")
                        st.rerun()
        
        # 投资建议
        st.subheader("🎯 AI投资建议")
        context = f"""
        总资产：{user_data.get('total_assets', 0)}万元
        股票占比：{user_data.get('stock_percentage', 30)}%
        风险偏好：{user_data.get('risk_level', '平衡')}
        今日金融新闻：{daily_updates.get('finance_news', '')}
        """

        investment_suggestion = get_cached_ai_suggestion(st.session_state.get('user_id', ''), context, 'investment')
        st.info(investment_suggestion)
        
        # 模拟收益图表
        st.subheader("📈 模拟收益趋势")
        
        dates = pd.date_range(start='2024-01-01', periods=365, freq='D')
        portfolio_value = [total_assets * 10000]
        
        for i in range(1, len(dates)):
            daily_return = 0.0008 if risk_level == '保守' else 0.0012 if risk_level == '稳健' else 0.0015
            portfolio_value.append(portfolio_value[-1] * (1 + daily_return + (0.002 * (np.random.randn()))))
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates,
            y=portfolio_value,
            mode='lines',
            name='Portfolio Value',
            line=dict(color='#4ECDC4', width=2)
        ))
        fig.update_layout(
            title='投资组合价值趋势',
            xaxis_title='日期',
            yaxis_title='价值（元）',
            hovermode='x'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("📰 金融资讯")
        if daily_updates:
            st.write(daily_updates.get('finance_news', '暂无更新'))
        
        st.subheader("⚠️ 风险提示")
        risk_tips = {
            '保守': "适合风险承受能力较低的投资者，建议配置更多固定收益类产品。",
            '稳健': "平衡风险与收益，建议适度配置权益类资产。",
            '平衡': "追求长期稳定增长，建议多元化配置。",
            '进取': "可承受一定波动，建议增加成长性资产配置。",
            '激进': "风险承受能力强，可考虑配置高风险高收益产品。"
        }
        st.warning(risk_tips.get(user_data.get('risk_level', '平衡'), ''))

def health_page():
    """健康页面"""
    st.title("🏥 健康管理")
    
    user_data = load_user_data(st.session_state.get('user_id', ''))
    daily_updates = load_daily_updates()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("健康数据")
        
        with st.form("health_form"):
            col_a, col_b = st.columns(2)
            
            with col_a:
                age = st.number_input("年龄", value=user_data.get('age', 35), min_value=1, max_value=120)
                height = st.number_input("身高(cm)", value=user_data.get('height', 170), min_value=100, max_value=250)
                weight = st.number_input("体重(kg)", value=user_data.get('weight', 70), min_value=30, max_value=200)
                blood_pressure = st.text_input("血压", value=user_data.get('blood_pressure', '120/80'))
            
            with col_b:
                exercise_freq = st.selectbox(
                    "运动频率",
                    ['从不', '偶尔(每月1-2次)', '每周1-2次', '每周3-4次', '每天'],
                    index=['从不', '偶尔(每月1-2次)', '每周1-2次', '每周3-4次', '每天'].index(
                        user_data.get('exercise_freq', '每周3-4次')
                    )
                )
                sleep_hours = st.slider("平均睡眠时长(小时)", 4, 12, user_data.get('sleep_hours', 7))
                smoke = st.selectbox("吸烟", ['否', '是'], index=0 if not user_data.get('smoke', False) else 1)
                drink = st.selectbox("饮酒", ['不饮酒', '偶尔', '经常'], 
                                    index=['不饮酒', '偶尔', '经常'].index(user_data.get('drink', '偶尔')))
            
            health_goals = st.text_area("健康目标", value=user_data.get('health_goals', ''), 
                                       placeholder="例如：减重10kg，改善睡眠质量等")
            
            if st.form_submit_button("保存健康数据"):
                bmi = weight / ((height/100) ** 2)
                health_score = calculate_health_score(age, bmi, exercise_freq, sleep_hours, smoke == '否')
                
                data = {
                    'age': age,
                    'height': height,
                    'weight': weight,
                    'blood_pressure': blood_pressure,
                    'exercise_freq': exercise_freq,
                    'sleep_hours': sleep_hours,
                    'smoke': smoke == '是',
                    'drink': drink,
                    'health_goals': health_goals,
                    'bmi': round(bmi, 1),
                    'health_score': health_score
                }
                
                if save_user_data(st.session_state['user_id'], data):
                    st.success("健康数据已更新")
                    st.rerun()
        
        # BMI分析
        if user_data.get('height') and user_data.get('weight'):
            st.subheader("📊 BMI分析")
            bmi = user_data.get('bmi', 0)
            
            col_1, col_2, col_3 = st.columns(3)
            with col_1:
                st.metric("BMI指数", f"{bmi:.1f}")
            with col_2:
                bmi_status = get_bmi_status(bmi)
                st.metric("状态", bmi_status)
            with col_3:
                st.metric("健康评分", f"{user_data.get('health_score', 85)}/100")
            
            # BMI趋势图（模拟数据）
            dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
            bmi_trend = [bmi + np.random.randn() * 0.2 for _ in range(30)]
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=dates,
                y=bmi_trend,
                mode='lines+markers',
                name='BMI趋势',
                line=dict(color='#FF6B6B', width=2)
            ))
            fig.add_hline(y=18.5, line_dash="dash", line_color="blue", annotation_text="偏瘦")
            fig.add_hline(y=24, line_dash="dash", line_color="green", annotation_text="正常")
            fig.add_hline(y=28, line_dash="dash", line_color="orange", annotation_text="偏胖")
            fig.update_layout(
                title='BMI趋势（近30天）',
                xaxis_title='日期',
                yaxis_title='BMI',
                hovermode='x'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # AI健康建议
        st.subheader("🤖 AI健康建议")
        context = f"""
        年龄：{user_data.get('age', 35)}岁
        BMI：{user_data.get('bmi', 23)}
        运动频率：{user_data.get('exercise_freq', '每周3-4次')}
        睡眠时长：{user_data.get('sleep_hours', 7)}小时
        健康目标：{user_data.get('health_goals', '保持健康')}
        今日健康贴士：{daily_updates.get('health_tips', '')}
        """

        health_suggestion = get_cached_ai_suggestion(st.session_state.get('user_id', ''), context, 'health')
        st.success(health_suggestion)
    
    with col2:
        st.subheader("💡 健康贴士")
        if daily_updates:
            st.info(daily_updates.get('health_tips', '暂无更新'))
        
        st.subheader("🎯 健康目标追踪")
        if user_data.get('health_goals'):
            st.write(user_data.get('health_goals'))
            progress = st.progress(0.7)
            st.caption("目标完成度：70%")
        else:
            st.info("请设置您的健康目标")
        
        st.subheader("⏰ 健康提醒")
        reminders = [
            "记得每小时起身活动5分钟",
            "今日饮水目标：2000ml",
            "晚上10点准备休息",
            "明天体检预约提醒"
        ]
        for reminder in reminders:
            st.checkbox(reminder)

def education_page():
    """教育页面"""
    st.title("🎓 教育规划")
    
    user_data = load_user_data(st.session_state.get('user_id', ''))
    daily_updates = load_daily_updates()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("教育信息")
        
        with st.form("education_form"):
            num_children = st.number_input("子女数量", value=user_data.get('num_children', 1), min_value=0, max_value=10)
            
            if num_children > 0:
                children_info = []
                for i in range(int(num_children)):
                    st.markdown(f"**孩子 {i+1}**")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        child_age = st.number_input(f"年龄", key=f"age_{i}", 
                                                   value=user_data.get(f'child_{i}_age', 10), 
                                                   min_value=0, max_value=30)
                        child_grade = st.selectbox(f"年级", key=f"grade_{i}",
                                                  options=['幼儿园', '小学', '初中', '高中', '大学', '其他'],
                                                  index=['幼儿园', '小学', '初中', '高中', '大学', '其他'].index(
                                                      user_data.get(f'child_{i}_grade', '小学')
                                                  ))
                    with col_b:
                        child_interests = st.text_input(f"兴趣特长", key=f"interests_{i}",
                                                      value=user_data.get(f'child_{i}_interests', ''))
                        child_goals = st.text_input(f"教育目标", key=f"goals_{i}",
                                                  value=user_data.get(f'child_{i}_goals', ''))
                    
                    children_info.append({
                        'age': child_age,
                        'grade': child_grade,
                        'interests': child_interests,
                        'goals': child_goals
                    })
                
                education_budget = st.number_input("年教育预算（万元）", 
                                                  value=user_data.get('education_budget', 10), 
                                                  min_value=0)
                
                education_plan = st.text_area("教育规划", 
                                             value=user_data.get('education_plan', ''),
                                             placeholder="描述您的教育规划和期望...")
                
                if st.form_submit_button("保存教育信息"):
                    data = {
                        'num_children': num_children,
                        'education_budget': education_budget,
                        'education_plan': education_plan
                    }
                    
                    for i, child in enumerate(children_info):
                        data[f'child_{i}_age'] = child['age']
                        data[f'child_{i}_grade'] = child['grade']
                        data[f'child_{i}_interests'] = child['interests']
                        data[f'child_{i}_goals'] = child['goals']
                    
                    # 计算教育进度
                    data['education_progress'] = calculate_education_progress(children_info)
                    
                    if save_user_data(st.session_state['user_id'], data):
                        st.success("教育信息已更新")
                        st.rerun()
            else:
                st.info("暂无子女教育规划")
                if st.form_submit_button("保存"):
                    data = {'num_children': 0, 'education_progress': 0}
                    save_user_data(st.session_state['user_id'], data)
        
        # 教育进度可视化
        if user_data.get('num_children', 0) > 0:
            st.subheader("📈 教育进度追踪")
            
            progress_data = []
            for i in range(int(user_data.get('num_children', 0))):
                progress_data.append({
                    '孩子': f"孩子{i+1}",
                    '当前阶段': user_data.get(f'child_{i}_grade', '未知'),
                    '进度': get_education_stage_progress(user_data.get(f'child_{i}_grade', '小学'))
                })
            
            if progress_data:
                df = pd.DataFrame(progress_data)
                fig = px.bar(df, x='孩子', y='进度', color='当前阶段',
                           color_discrete_sequence=['#4ECDC4', '#45B7D1', '#96E6B3'])
                fig.update_layout(yaxis_title='教育进度(%)')
                st.plotly_chart(fig, use_container_width=True)
        
        # AI教育建议
        st.subheader("🤖 AI教育建议")
        
        children_context = ""
        for i in range(int(user_data.get('num_children', 0))):
            children_context += f"""
            孩子{i+1}：{user_data.get(f'child_{i}_age', 0)}岁，
            {user_data.get(f'child_{i}_grade', '未知')}，
            兴趣：{user_data.get(f'child_{i}_interests', '未知')}，
            目标：{user_data.get(f'child_{i}_goals', '未知')}
            """
        
        context = f"""
        子女数量：{user_data.get('num_children', 0)}
        {children_context}
        教育预算：{user_data.get('education_budget', 0)}万元/年
        教育规划：{user_data.get('education_plan', '未设定')}
        今日教育资讯：{daily_updates.get('education_info', '')}
        """

        education_suggestion = get_cached_ai_suggestion(st.session_state.get('user_id', ''), context, 'education')
        st.info(education_suggestion)
    
    with col2:
        st.subheader("📚 教育资讯")
        if daily_updates:
            st.write(daily_updates.get('education_info', '暂无更新'))
        
        st.subheader("🎯 教育里程碑")
        milestones = {
            '幼儿园': ['语言发展', '社交能力', '基础认知'],
            '小学': ['基础学科', '兴趣培养', '学习习惯'],
            '初中': ['学科深化', '青春期引导', '中考准备'],
            '高中': ['高考准备', '专业选择', '综合素质'],
            '大学': ['专业学习', '实习就业', '人生规划']
        }
        
        for i in range(int(user_data.get('num_children', 0))):
            grade = user_data.get(f'child_{i}_grade', '小学')
            if grade in milestones:
                st.write(f"**孩子{i+1} - {grade}阶段重点**")
                for milestone in milestones[grade]:
                    st.write(f"• {milestone}")

def life_planning_page():
    """人生规划页面"""
    st.title("🎯 人生规划")
    
    user_data = load_user_data(st.session_state.get('user_id', ''))
    
    st.subheader("人生目标设定")
    
    with st.form("life_planning_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            life_stage = st.selectbox(
                "当前人生阶段",
                ['学习成长期', '事业发展期', '家庭稳定期', '财富积累期', '退休规划期'],
                index=['学习成长期', '事业发展期', '家庭稳定期', '财富积累期', '退休规划期'].index(
                    user_data.get('life_stage', '事业发展期')
                )
            )
            
            short_term_goals = st.text_area(
                "短期目标（1-2年）",
                value=user_data.get('short_term_goals', ''),
                placeholder="例如：升职加薪、买房买车、健身减重等"
            )
            
            medium_term_goals = st.text_area(
                "中期目标（3-5年）",
                value=user_data.get('medium_term_goals', ''),
                placeholder="例如：创业、子女教育、资产增值等"
            )
        
        with col2:
            long_term_goals = st.text_area(
                "长期目标（5年以上）",
                value=user_data.get('long_term_goals', ''),
                placeholder="例如：财务自由、环游世界、退休规划等"
            )
            
            life_vision = st.text_area(
                "人生愿景",
                value=user_data.get('life_vision', ''),
                placeholder="描述您理想中的人生状态..."
            )
            
            priorities = st.multiselect(
                "优先级排序",
                ['事业发展', '家庭和谐', '健康长寿', '财富积累', '个人成长', '社会贡献'],
                default=user_data.get('priorities', ['家庭和谐', '健康长寿'])
            )
        
        if st.form_submit_button("保存规划"):
            life_score = calculate_life_score(user_data)
            
            data = {
                'life_stage': life_stage,
                'short_term_goals': short_term_goals,
                'medium_term_goals': medium_term_goals,
                'long_term_goals': long_term_goals,
                'life_vision': life_vision,
                'priorities': priorities,
                'life_score': life_score
            }
            
            if save_user_data(st.session_state['user_id'], data):
                st.success("人生规划已更新")
                st.rerun()
    
    # 人生规划仪表盘
    st.subheader("📊 综合评估")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # 雷达图 - 人生各维度评分
        categories = ['财富', '健康', '教育', '家庭', '事业', '成长']
        values = [
            user_data.get('wealth_score', 70),
            user_data.get('health_score', 85),
            user_data.get('education_progress', 75),
            user_data.get('family_score', 90),
            user_data.get('career_score', 80),
            user_data.get('growth_score', 75)
        ]
        
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=categories,
            fill='toself',
            name='当前状态'
        ))
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 100]
                )
            ),
            showlegend=False,
            title="人生平衡轮"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # 目标完成度
        st.metric("综合评分", f"{user_data.get('life_score', 88)}/100")
        
        goals_progress = {
            '短期目标': 75,
            '中期目标': 45,
            '长期目标': 20
        }
        
        for goal, progress in goals_progress.items():
            st.write(f"**{goal}**")
            st.progress(progress/100)
            st.caption(f"完成度：{progress}%")
    
    with col3:
        # 优先事项提醒
        st.write("**本月重点事项**")
        
        monthly_focus = [
            "完成投资组合调整",
            "年度体检预约",
            "孩子期末考试准备",
            "家庭旅行计划"
        ]
        
        for item in monthly_focus:
            st.checkbox(item, key=f"focus_{item}")
    
    # AI综合建议
    st.subheader("🤖 AI人生规划建议")
    
    context = f"""
    人生阶段：{user_data.get('life_stage', '事业发展期')}
    短期目标：{user_data.get('short_term_goals', '未设定')}
    中期目标：{user_data.get('medium_term_goals', '未设定')}
    长期目标：{user_data.get('long_term_goals', '未设定')}
    人生愿景：{user_data.get('life_vision', '未设定')}
    优先级：{user_data.get('priorities', [])}
    财富状况：{user_data.get('total_assets', 0)}万元
    健康评分：{user_data.get('health_score', 85)}/100
    教育进度：{user_data.get('education_progress', 75)}%
    """
    
    life_suggestion = get_cached_ai_suggestion(st.session_state.get('user_id', ''), context, 'life')
    st.success(life_suggestion)
    
    # 行动计划
    st.subheader("📝 行动计划")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**本周待办**")
        weekly_tasks = st.text_area("", placeholder="输入本周待办事项...", key="weekly_tasks")
        if st.button("保存周计划"):
            st.success("周计划已保存")
    
    with col2:
        st.write("**本月目标**")
        monthly_goals = st.text_area("", placeholder="输入本月目标...", key="monthly_goals")
        if st.button("保存月目标"):
            st.success("月目标已保存")

def profile_page():
    """个人信息页面"""
    st.title("👤 个人信息")
    
    user_data = load_user_data(st.session_state.get('user_id', ''))
    
    st.subheader("基本信息")
    
    with st.form("profile_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("姓名", value=user_data.get('name', ''))
            email = st.text_input("邮箱", value=user_data.get('email', ''))
            phone = st.text_input("手机", value=user_data.get('phone', ''))
            birth_date = st.date_input("出生日期", value=datetime.now().date())
        
        with col2:
            gender = st.selectbox("性别", ['男', '女', '其他'], 
                                 index=['男', '女', '其他'].index(user_data.get('gender', '男')))
            occupation = st.text_input("职业", value=user_data.get('occupation', ''))
            city = st.text_input("所在城市", value=user_data.get('city', ''))
            marital_status = st.selectbox("婚姻状况", ['未婚', '已婚', '离异', '丧偶'],
                                         index=['未婚', '已婚', '离异', '丧偶'].index(
                                             user_data.get('marital_status', '已婚')
                                         ))
        
        if st.form_submit_button("更新基本信息"):
            data = {
                'name': name,
                'email': email,
                'phone': phone,
                'birth_date': birth_date.isoformat(),
                'gender': gender,
                'occupation': occupation,
                'city': city,
                'marital_status': marital_status
            }
            
            if save_user_data(st.session_state['user_id'], data):
                st.success("基本信息已更新")
                st.rerun()
    
    # 数据概览
    st.subheader("📊 数据概览")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.info(f"**资产总额**\n¥{user_data.get('total_assets', 0):,.0f}万")
    
    with col2:
        st.success(f"**健康评分**\n{user_data.get('health_score', 85)}/100")
    
    with col3:
        st.warning(f"**教育进度**\n{user_data.get('education_progress', 75)}%")
    
    with col4:
        st.error(f"**人生评分**\n{user_data.get('life_score', 88)}/100")
    
    # 数据导出
    st.subheader("📥 数据管理")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("导出个人数据"):
            # 这里应该生成CSV或JSON文件供下载
            st.success("数据导出成功！")
            st.download_button(
                label="下载数据",
                data=json.dumps(user_data, ensure_ascii=False, indent=2),
                file_name=f"personal_data_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json"
            )
    
    with col2:
        if st.button("清除所有数据", type="secondary"):
            st.warning("⚠️ 此操作将删除所有个人数据，是否确认？")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("确认删除", type="primary"):
                    # 清除数据逻辑
                    st.success("数据已清除")
            with col_b:
                if st.button("取消"):
                    st.info("操作已取消")
    
    # 账户设置
    st.subheader("⚙️ 账户设置")
    
    with st.expander("通知设置"):
        st.checkbox("接收每日资讯推送", value=user_data.get('daily_news', True))
        st.checkbox("接收投资建议提醒", value=user_data.get('investment_alert', True))
        st.checkbox("接收健康提醒", value=user_data.get('health_reminder', True))
        st.checkbox("接收教育进度更新", value=user_data.get('education_update', False))
        
        if st.button("保存通知设置"):
            st.success("通知设置已更新")
    
    with st.expander("隐私设置"):
        st.checkbox("允许AI分析个人数据", value=True)
        st.checkbox("参与用户体验改进计划", value=False)
        st.checkbox("数据加密存储", value=True, disabled=True)
        
        if st.button("保存隐私设置"):
            st.success("隐私设置已更新")

# 辅助函数
def calculate_health_score(age, bmi, exercise_freq, sleep_hours, no_smoke):
    """计算健康评分"""
    score = 100
    
    # BMI评分
    if bmi < 18.5 or bmi > 30:
        score -= 20
    elif bmi < 20 or bmi > 25:
        score -= 10
    
    # 运动评分
    exercise_scores = {'从不': -20, '偶尔(每月1-2次)': -10, '每周1-2次': 0, '每周3-4次': 5, '每天': 10}
    score += exercise_scores.get(exercise_freq, 0)
    
    # 睡眠评分
    if sleep_hours < 6 or sleep_hours > 9:
        score -= 10
    elif sleep_hours < 7 or sleep_hours > 8:
        score -= 5
    
    # 吸烟评分
    if not no_smoke:
        score -= 15
    
    # 年龄调整
    if age > 60:
        score -= 5
    elif age < 25:
        score += 5
    
    return max(0, min(100, score))

def get_bmi_status(bmi):
    """获取BMI状态"""
    if bmi < 18.5:
        return "偏瘦"
    elif 18.5 <= bmi < 24:
        return "正常"
    elif 24 <= bmi < 28:
        return "偏胖"
    else:
        return "肥胖"

def get_education_stage_progress(grade):
    """获取教育阶段进度"""
    stages = {
        '幼儿园': ['语言发展', '社交能力', '基础认知'],
        '小学': ['基础学科', '兴趣培养', '学习习惯'],
        '初中': ['学科深化', '青春期引导', '中考准备'],
        '高中': ['高考准备', '专业选择', '综合素质'],
        '大学': ['专业学习', '实习就业', '人生规划']
    }
    
    if grade in stages:
        return len(stages[grade])
    else:
        return 0    # 未知阶段

def calculate_education_progress(children_info: List[Dict[str, Any]]) -> int:
    """根据孩子信息估算教育进度（0-100）"""
    if not children_info:
        return 0
    total = 0
    for child in children_info:
        grade = child.get('grade', '')
        # map stage to progress
        mapping = {'幼儿园': 20, '小学': 40, '初中': 60, '高中': 80, '大学': 95, '其他': 50}
        total += mapping.get(grade, 0)
    return int(total / len(children_info))

def calculate_life_score(user_data: Dict[str, Any]) -> int:
    """粗略计算人生规划得分，基于财富、健康、教育的简单加权"""
    wealth = user_data.get('wealth_score', user_data.get('total_assets', 0) and 70 or 50)
    health = user_data.get('health_score', 50)
    education = user_data.get('education_progress', 50)

    # weights: wealth 40%, health 30%, education 30%
    score = 0.4 * wealth + 0.3 * health + 0.3 * education
    return int(max(0, min(100, score)))


# --- App entry: initialize and route pages ---
init_database()
authenticate_user()

# start scheduler once per session
try:
    start_scheduler_in_background()
except Exception:
    pass

# If not logged in, stop here
if not st.session_state.get('authentication_status'):
    st.stop()

# Top-center navigation (replaces sidebar radio)
pages = {
    '仪表盘': dashboard_page,
    '投资': investment_page,
    '健康': health_page,
    '教育': education_page,
    '人生规划': life_planning_page,
    '个人信息': profile_page
}

tabs = st.tabs(list(pages.keys()))
# Streamlit tabs return a list of tab objects; render the selected page within each tab's context
for tab_obj, label in zip(tabs, list(pages.keys())):
    with tab_obj:
        # Each tab calls its page function
        pages[label]()
