# app.py
import os
import sys
import subprocess

import streamlit as st
import pandas as pd

from crawler import (
    crawl_kakao_reviews,
    crawl_google_reviews,
    crawl_naver_reviews,
)
from analysis import (
    analyze_reviews,
    generate_prompt,
    generate_consumer_prompt,
)

# ──────────────────────────────────────────────────────────────────────────────
# 페이지 설정
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="리뷰 분석 앱", layout="wide")
st.title("🍽️ 식당 리뷰 크롤링 & 분석")


# ──────────────────────────────────────────────────────────────────────────────
# 1) 세션 스테이트 초기화
# ──────────────────────────────────────────────────────────────────────────────
if 'submitted' not in st.session_state:
    st.session_state.submitted = False

if 'last_name' not in st.session_state:
    st.session_state.last_name = ""


# ──────────────────────────────────────────────────────────────────────────────
# 2) 사이드바 폼
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    with st.form('control_form'):
        restaurant_name = st.text_input(
            "식당 이름을 정확히 입력해주세요.(지점 및 띄어쓰기 포함)",
            help="예: '버거킹 연세로점', '장정정 선릉 본점' 등으로 정확히 입력"
        )
        user_type = st.radio("모드 선택", ("식당주인용", "고객용"))
        submitted_click = st.form_submit_button("🔍 분석 시작")

# 3) “분석 시작” 버튼이 눌리면 submitted=True로, 
#    그리고 식당 이름이 바뀌면 이전 prompt를 삭제
if submitted_click:
    st.session_state.submitted = True
    if restaurant_name != st.session_state.last_name:
        if 'prompt' in st.session_state:
            del st.session_state['prompt']
        st.session_state.last_name = restaurant_name

# 4) 분석 전 대기
if not st.session_state.submitted:
    st.info("사이드바에서 식당 이름을 입력하고 ‘분석 시작’ 버튼을 눌러 주세요.")
    st.stop()

# 5) 입력 검증
if not restaurant_name:
    st.warning("식당 이름을 입력하세요.")
    st.stop()


# ──────────────────────────────────────────────────────────────────────────────
# 6) 크롤링 (한 번만 실행, 캐시)
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_all_reviews(name: str):
    kakao = crawl_kakao_reviews(name)
    google = crawl_google_reviews(name)
    naver = crawl_naver_reviews(name)
    return kakao + google + naver

with st.spinner("1/3 크롤링 중…"):
    all_reviews = get_all_reviews(restaurant_name)

if not all_reviews:
    st.error("리뷰를 찾지 못했습니다.")
    st.stop()


# ──────────────────────────────────────────────────────────────────────────────
# 7) 원본 리뷰 테이블
# ──────────────────────────────────────────────────────────────────────────────
df = pd.DataFrame(all_reviews)
st.subheader("✅ 수집된 원본 리뷰")
# 식당 이름 컬럼도 같이 보여주도록 변경
st.dataframe(df[["platform","restaurant_name","reviewer","text","rating","date"]], height=300)


# ──────────────────────────────────────────────────────────────────────────────
# 8) 플랫폼별 실제 식당 이름 보여주기
# ──────────────────────────────────────────────────────────────────────────────
st.subheader("📍 플랫폼별 리뷰를 가져온 식당 이름")
platform_names = df[["platform", "restaurant_name"]].drop_duplicates().reset_index(drop=True)
st.table(platform_names)


# ──────────────────────────────────────────────────────────────────────────────
# 9) 감성·키워드 분석
# ──────────────────────────────────────────────────────────────────────────────
with st.spinner("2/3 감성 분석 및 키워드 추출…"):
    df_proc, keywords, pos_ratio, neg_ratio, top_pos, top_neg, aspects, total = analyze_reviews(df)


# ──────────────────────────────────────────────────────────────────────────────
# 10) 프롬프트 생성
# ──────────────────────────────────────────────────────────────────────────────
if 'prompt' not in st.session_state:
    if user_type == "식당주인용":
        df_kw = pd.DataFrame({
            aspect: [", ".join(f"{w}({s:.2f})" for w, s in kws)]
            for aspect, kws in keywords.items()
        }, index=["키워드"]).T
        st.subheader("🔑 핵심 키워드 (테이블)")
        st.table(df_kw)
        st.write(f"긍정 비율: {pos_ratio:.1f}%  |  부정 비율: {neg_ratio:.1f}%")

        with st.spinner("3/3 주인용 LLM 프롬프트 생성…"):
            prompt = generate_prompt(
                name=restaurant_name,
                keywords=keywords,
                pos_ratio=pos_ratio,
                neg_ratio=neg_ratio,
                aspects=aspects,
                top_pos=top_pos,
                top_neg=top_neg,
                classified_count=total
            )
    else:
        with st.spinner("3/3 고객용 LLM 프롬프트 생성…"):
            prompt = generate_consumer_prompt(
                name=restaurant_name,
                keywords=keywords,
                pos_ratio=pos_ratio,
                neg_ratio=neg_ratio,
                aspects=aspects,
                top_pos=top_pos,
                top_neg=top_neg,
                classified_count=total
            )
    st.session_state['prompt'] = prompt

prompt = st.session_state['prompt']


# ──────────────────────────────────────────────────────────────────────────────
# 11) 프롬프트 출력
# ──────────────────────────────────────────────────────────────────────────────
st.subheader("📝 LLM 요청 프롬프트")
st.code(prompt, language="plain")


# ──────────────────────────────────────────────────────────────────────────────
# 12) Gemini 전송 버튼
# ──────────────────────────────────────────────────────────────────────────────
if st.button("🔗 Gemini에 전송"):
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    send_script = os.path.join(script_dir, "send_prompt.py")
    subprocess.Popen([sys.executable, send_script, prompt])
    st.success("Gemini 전송 스크립트를 실행했습니다. 브라우저 창을 확인해주세요.")
