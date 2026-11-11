# config.py
# 统一读取密钥。
# 本地运行时读 .env 文件；部署到 Streamlit Community Cloud 后读平台上的 Secrets。
# 两边的键名完全一样，所以代码不用改。

import os


def load_env():
    """加载项目根目录下的 .env（本地开发用）。没装 python-dotenv 也不报错。"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass


def get_secret(key: str, default: str = "") -> str:
    """先找环境变量（.env），再找 Streamlit Secrets，都没有就返回默认值。"""
    value = os.getenv(key)
    if value:
        return value.strip()

    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        # 不在 Streamlit 环境里（比如单独跑测试脚本）时忽略
        pass

    return default


def has_llm_key() -> bool:
    return bool(get_secret("ARK_API_KEY"))


def has_asr_key() -> bool:
    return bool(get_secret("VOLC_APP_ID")) and bool(
        get_secret("VOLC_ACCESS_KEY") or get_secret("VOLC_ASR_TOKEN"))


load_env()
