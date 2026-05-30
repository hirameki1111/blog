# -*- coding: utf-8 -*-
"""
키워드 + 관련 자료(txt/pdf) + 관점 + 스타일을 입력받아
GPT API로 창의적인 블로그 글을 생성하는 Streamlit 웹 앱.

[로컬 실행]
  streamlit run streamlit_app.py

[배포]
  GitHub에 push 후 https://share.streamlit.io 에서 이 파일을 진입점으로 지정.
  OpenAI API 키는 Streamlit Cloud의 Secrets에 OPENAI_API_KEY 로 등록한다.
"""

import io
import os

import streamlit as st

# 글 생성 핵심 로직은 기존 blog_writer 모듈을 재사용한다.
from blog_writer import (
    DEFAULT_MODEL,
    DEFAULT_STYLE,
    MAX_MATERIAL_CHARS,
    STYLE_GUIDES,
    build_messages,
)


# ---------------- API 키 준비 ----------------
def _resolve_api_key() -> str:
    """Streamlit Secrets 또는 환경변수에서 API 키를 가져온다."""
    key = ""
    try:
        key = st.secrets.get("OPENAI_API_KEY", "")  # 배포 환경
    except Exception:
        key = ""
    if not key:
        key = os.getenv("OPENAI_API_KEY", "")  # 로컬 환경변수
    return (key or "").strip()


# ---------------- 업로드 파일에서 텍스트 추출 ----------------
def _extract_uploaded(file) -> str:
    """Streamlit 업로드 파일(txt/pdf/md)에서 텍스트를 추출한다."""
    name = file.name.lower()
    data = file.getvalue()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(pages)
    # txt / md 등: 여러 인코딩 시도
    for enc in ("utf-8", "utf-8-sig", "cp949"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


def _build_material(files) -> tuple[str, list[str]]:
    """업로드 파일 목록을 하나의 자료 문자열로 합친다."""
    chunks, loaded = [], []
    for f in files or []:
        try:
            text = _extract_uploaded(f).strip()
        except Exception as e:
            st.warning(f"'{f.name}' 을 읽지 못했습니다: {e}")
            continue
        if not text:
            st.warning(f"'{f.name}' 의 내용이 비어 있어 건너뜁니다. (스캔 PDF일 수 있음)")
            continue
        chunks.append(f"### 자료: {f.name}\n{text}")
        loaded.append(f.name)

    combined = "\n\n".join(chunks)
    if len(combined) > MAX_MATERIAL_CHARS:
        combined = combined[:MAX_MATERIAL_CHARS] + "\n\n...(자료가 길어 일부만 사용)"
    return combined, loaded


def generate(keyword, material, viewpoint, style, api_key) -> str:
    """OpenAI API로 블로그 글을 생성한다."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=build_messages(keyword, material, viewpoint, style),
        temperature=0.9,
        max_tokens=2000,
        top_p=0.95,
        presence_penalty=0.3,
    )
    return resp.choices[0].message.content.strip()


# ---------------- UI ----------------
st.set_page_config(page_title="창의적 블로그 글 생성기", page_icon="✍️", layout="centered")
st.title("✍️ 키워드 → 창의적 블로그 글 생성기")
st.caption(f"GPT API 기반 · 모델: {DEFAULT_MODEL}")

api_key = _resolve_api_key()
if not api_key:
    st.error(
        "OpenAI API 키가 없습니다.\n\n"
        "- **로컬**: 환경변수 `OPENAI_API_KEY` 설정\n"
        "- **배포(Streamlit Cloud)**: 앱 Settings → Secrets 에 "
        "`OPENAI_API_KEY = \"sk-...\"` 추가"
    )

keyword = st.text_input("키워드", placeholder="예: 경주 가을여행")

files = st.file_uploader(
    "관련 자료 파일 (txt / pdf / md) — 여러 개 가능",
    type=["txt", "pdf", "md"],
    accept_multiple_files=True,
)

viewpoint = st.text_area(
    "나의 관점 (200자 내외, 선택)",
    placeholder="이 글에 담고 싶은 시각·주장을 적어주세요.",
    height=100,
)
st.caption(f"{len(viewpoint)} / 200자")

style = st.radio("글 스타일", list(STYLE_GUIDES.keys()),
                 index=list(STYLE_GUIDES.keys()).index(DEFAULT_STYLE),
                 horizontal=True)

if st.button("블로그 글 생성", type="primary", disabled=not api_key):
    if not keyword.strip():
        st.warning("키워드를 입력해 주세요.")
    else:
        with st.spinner("글을 생성하는 중입니다..."):
            try:
                material, loaded = _build_material(files)
                post = generate(keyword.strip(), material, viewpoint.strip(), style, api_key)
                st.session_state["post"] = post
                st.session_state["loaded"] = loaded
            except Exception as e:
                st.error(f"글 생성 중 오류가 발생했습니다: {e}")

# 결과 표시
if st.session_state.get("post"):
    loaded = st.session_state.get("loaded", [])
    info = f"자료 {len(loaded)}개 반영" if loaded else "자료 없음"
    st.success(f"완료 — [{style}] {info}")
    st.markdown("---")
    st.markdown(st.session_state["post"])
    st.download_button(
        "📥 마크다운(.md) 다운로드",
        data=st.session_state["post"],
        file_name=f"blog_{keyword.strip() or 'post'}.md",
        mime="text/markdown",
    )
