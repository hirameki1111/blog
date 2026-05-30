# -*- coding: utf-8 -*-
"""
키워드 + 관련 자료(텍스트 파일)를 입력받아 GPT API로
창의적인 블로그 글을 생성하는 프로그램.

[가성비 모델 선택]
- 창의적 블로그 글은 '장문 생성' 작업이라 출력 토큰 비용이 비용의 대부분을 차지합니다.
- gpt-4o-mini는 GPT-4 계열의 글쓰기 품질에 근접하면서도
  gpt-4o 대비 약 1/30 수준의 저렴한 가격을 제공합니다.
- 따라서 '창의적 장문 생성'에는 gpt-4o-mini가 가성비가 가장 뛰어납니다.
- 필요 시 환경변수 OPENAI_MODEL 로 다른 모델(gpt-4.1-mini 등)로 교체할 수 있습니다.

[사용법]
  # 키워드 + 자료 파일 1개
  python blog_writer.py 가을여행 자료.txt

  # 키워드 + 자료 파일 여러 개
  python blog_writer.py 가을여행 자료1.txt 자료2.txt

  # 키워드 + 글쓴이 관점(200자 내외)
  python blog_writer.py 가을여행 자료.txt --viewpoint "나는 가을이 사색의 계절이라고 본다..."

  # 인자 없이 실행하면 키워드 / 자료 파일 / 관점을 차례로 물어봅니다.
  python blog_writer.py
"""

import os
import sys

from openai import OpenAI

# 기본 모델: 가성비가 가장 좋은 gpt-4o-mini
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# 자료가 지나치게 길 때 프롬프트에 넣을 최대 글자 수(토큰 비용 방어)
MAX_MATERIAL_CHARS = 12000


def _read_text_file(path: str) -> str:
    """일반 텍스트 파일을 여러 인코딩으로 시도해 읽는다."""
    for enc in ("utf-8", "utf-8-sig", "cp949"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError("인코딩을 해석할 수 없습니다 (utf-8/cp949 실패)")


def _read_pdf_file(path: str) -> str:
    """PDF 파일에서 텍스트를 추출한다. pypdf 또는 PyPDF2를 사용한다."""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # 구버전 호환
        except ImportError:
            raise ValueError(
                "PDF를 읽으려면 pypdf가 필요합니다. 'pip install pypdf'로 설치하세요."
            )

    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(pages)


def read_one_file(path: str) -> str:
    """확장자에 따라 txt 또는 pdf 파일의 텍스트 내용을 반환한다."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _read_pdf_file(path)
    # .txt, .md 등 그 외는 텍스트로 처리
    return _read_text_file(path)


def read_material_files(paths):
    """자료 파일들(txt/pdf)을 읽어 하나의 문자열로 합친다.

    반환: (합쳐진 자료 문자열, 실제로 읽은 파일 목록)
    """
    chunks = []
    loaded = []
    for path in paths:
        if not os.path.isfile(path):
            print(f"[경고] 자료 파일을 찾을 수 없어 건너뜁니다: {path}")
            continue

        try:
            text = read_one_file(path)
        except Exception as e:
            print(f"[경고] 파일을 읽지 못해 건너뜁니다: {path} ({e})")
            continue

        text = (text or "").strip()
        if not text:
            print(f"[경고] 내용이 비어 있어 건너뜁니다: {path}")
            continue

        filename = os.path.basename(path)
        chunks.append(f"### 자료: {filename}\n{text}")
        loaded.append(path)

    combined = "\n\n".join(chunks)

    # 너무 길면 잘라서 비용/토큰 한도를 보호
    if len(combined) > MAX_MATERIAL_CHARS:
        combined = combined[:MAX_MATERIAL_CHARS] + "\n\n...(자료가 길어 일부만 사용)"

    return combined, loaded


# 선택 가능한 글 스타일과 각 스타일의 작성 지침
STYLE_GUIDES = {
    "친근하게": (
        "친근하고 다정한 말투로 쓴다. 독자에게 말을 거는 듯한 구어체와 '~해요', "
        "'~죠' 같은 부드러운 어미를 사용하고, 적절한 이모지나 위트로 친밀감을 준다."
    ),
    "진지하게": (
        "진지하고 차분한 말투로 쓴다. '~다', '~입니다'체의 격식 있는 문장과 "
        "논리적인 흐름을 유지하며, 신뢰감 있고 깊이 있는 통찰을 담는다."
    ),
}
DEFAULT_STYLE = "친근하게"


def build_messages(keyword: str, material: str = "", viewpoint: str = "", style: str = ""):
    """창의성을 끌어올리기 위한 시스템/유저 프롬프트를 구성한다.

    viewpoint: 글쓴이(사용자)의 관점·주장·논조. 글 전체에 반영된다.
    style: 글의 말투/스타일 (예: '친근하게', '진지하게').
    """
    system_prompt = (
        "당신은 수많은 독자를 사로잡는 베테랑 블로그 작가입니다. "
        "주어진 키워드와 참고 자료를 바탕으로 독창적이고 흥미로운 한국어 블로그 글을 씁니다. "
        "다음 원칙을 지키세요:\n"
        "1. 시선을 끄는 매력적인 제목을 만든다.\n"
        "2. 도입부에서 호기심을 자극하는 질문이나 일화로 시작한다.\n"
        "3. 비유, 스토리텔링, 구체적인 예시를 적극 활용한다.\n"
        "4. 소제목(##)으로 글을 읽기 쉽게 구조화한다.\n"
        "5. 참고 자료가 주어지면, 그 안의 사실·정보·수치를 글에 자연스럽게 녹여낸다. "
        "자료에 없는 내용을 사실처럼 지어내지 않는다.\n"
        "6. 글쓴이의 관점이 주어지면, 그 관점·주장·논조를 글 전체를 관통하는 "
        "핵심 메시지로 삼아 일관되게 반영한다.\n"
        "7. 마지막에 독자에게 생각할 거리를 남기는 마무리를 한다.\n"
        "출력은 마크다운 형식으로 작성하세요."
    )

    # 스타일 지침을 시스템 프롬프트에 덧붙인다.
    if style:
        guide = STYLE_GUIDES.get(style)
        if guide:
            system_prompt += f"\n\n[글의 스타일: {style}] {guide}"
        else:
            system_prompt += f"\n\n[글의 스타일] {style}"

    parts = [f"키워드: '{keyword}'"]

    if viewpoint:
        parts.append(
            "글쓴이의 관점(이 시각과 논조를 글 전체에 일관되게 반영해 주세요):\n"
            f"\"{viewpoint}\""
        )

    if material:
        parts.append(
            "아래는 참고 자료입니다. 이 자료의 내용을 적극 반영하되, "
            "창의적이고 독자가 끝까지 읽고 싶어지는 블로그 글로 재구성해 주세요.\n\n"
            f"=== 참고 자료 시작 ===\n{material}\n=== 참고 자료 끝 ==="
        )
    else:
        parts.append(
            "위 내용을 바탕으로 창의적이고 독자가 끝까지 읽고 싶어지는 "
            "블로그 글을 작성해 주세요."
        )

    user_prompt = "\n\n".join(parts)

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def generate_blog_post(
    keyword: str,
    material: str = "",
    viewpoint: str = "",
    style: str = "",
    model: str = DEFAULT_MODEL,
) -> str:
    """키워드, 참고 자료, 글쓴이 관점, 스타일을 받아 블로그 글을 생성해 반환한다."""
    # 환경변수에 줄바꿈/공백이 섞여 있으면 HTTP 헤더 오류가 나므로 정리한다.
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=build_messages(keyword, material, viewpoint, style),
        temperature=0.9,        # 창의성을 위해 높게 설정
        max_tokens=2000,        # 충분한 길이의 글
        top_p=0.95,
        presence_penalty=0.3,   # 다양한 표현 유도
    )
    return response.choices[0].message.content.strip()


def main():
    if not os.getenv("OPENAI_API_KEY"):
        print("[오류] 환경변수 OPENAI_API_KEY 가 설정되어 있지 않습니다.")
        print('  PowerShell:  $env:OPENAI_API_KEY = "sk-..."')
        sys.exit(1)

    # 인자 파싱: 첫 번째 = 키워드, 나머지 = 자료 파일 경로
    # (관점/스타일은 대화형으로 입력받거나 --viewpoint, --style 옵션으로 줄 수 있다.)
    viewpoint = ""
    style = ""
    if len(sys.argv) > 1:
        keyword = sys.argv[1].strip()
        rest = sys.argv[2:]
        # --viewpoint "..." 옵션이 있으면 분리
        if "--viewpoint" in rest:
            i = rest.index("--viewpoint")
            viewpoint = rest[i + 1].strip() if i + 1 < len(rest) else ""
            rest = rest[:i] + rest[i + 2:]
        # --style "..." 옵션이 있으면 분리
        if "--style" in rest:
            i = rest.index("--style")
            style = rest[i + 1].strip() if i + 1 < len(rest) else ""
            rest = rest[:i] + rest[i + 2:]
        material_paths = rest
    else:
        keyword = input("블로그 키워드 1개를 입력하세요: ").strip()
        raw = input(
            "관련 자료 파일 경로를 입력하세요 (txt/pdf, 여러 개는 공백/쉼표로 구분, 없으면 Enter): "
        ).strip()
        material_paths = [p for p in raw.replace(",", " ").split() if p]
        viewpoint = input(
            "글에 담고 싶은 당신의 관점을 200자 내외로 입력하세요 (없으면 Enter): "
        ).strip()
        style = input(
            "글 스타일을 선택하세요 (친근하게 / 진지하게, 기본=친근하게): "
        ).strip() or DEFAULT_STYLE

    if not keyword:
        print("[오류] 키워드를 입력해야 합니다.")
        sys.exit(1)

    # 관점이 너무 길면 200자 내외로 권장 (잘라내지는 않고 안내만)
    if len(viewpoint) > 300:
        print(f"[안내] 관점이 다소 깁니다({len(viewpoint)}자). 200자 내외를 권장합니다.")

    # 자료 파일 읽기
    material, loaded = read_material_files(material_paths)
    if loaded:
        print(f"\n참고 자료 {len(loaded)}개를 불러왔습니다: {', '.join(os.path.basename(p) for p in loaded)}")
    else:
        print("\n참고 자료 없이 키워드만으로 글을 생성합니다.")

    if viewpoint:
        print(f"글쓴이 관점을 반영합니다: \"{viewpoint[:50]}{'...' if len(viewpoint) > 50 else ''}\"")

    if style:
        print(f"글 스타일: {style}")

    print(f"'{keyword}' 키워드로 블로그 글을 생성하는 중... (모델: {DEFAULT_MODEL})\n")

    try:
        post = generate_blog_post(keyword, material, viewpoint, style)
    except Exception as e:
        print(f"[오류] 글 생성 중 문제가 발생했습니다: {e}")
        sys.exit(1)

    print("=" * 60)
    print(post)
    print("=" * 60)

    # 파일로도 저장
    safe_name = "".join(c for c in keyword if c.isalnum() or c in " _-").strip()
    filename = f"blog_{safe_name or 'post'}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(post)
    print(f"\n글이 '{filename}' 파일로 저장되었습니다.")


if __name__ == "__main__":
    main()
