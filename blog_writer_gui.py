# -*- coding: utf-8 -*-
"""
키워드 + 관련 자료 파일(txt/pdf)을 GUI로 첨부해
GPT API로 창의적인 블로그 글을 생성하는 프로그램 (Tkinter GUI 버전).

[실행]
  python blog_writer_gui.py

- "파일 첨부" 버튼으로 txt / pdf 자료를 여러 개 추가할 수 있습니다.
- "나의 관점"(200자 내외)과 "글 스타일"(친근하게 / 진지하게)을 선택할 수 있습니다.
- 키워드를 입력하고 "블로그 글 생성"을 누르면 GPT API가 글을 작성합니다.
- 생성된 글은 화면에 표시되고, "저장" 버튼으로 .md 파일로 저장할 수 있습니다.
- "초기화" 버튼으로 모든 입력과 결과를 처음 상태로 되돌릴 수 있습니다.

API 키는 환경변수 OPENAI_API_KEY 에서 읽습니다.
"""

import os
import threading

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# 글 생성 로직은 기존 blog_writer 모듈을 재사용한다.
from blog_writer import (
    DEFAULT_MODEL,
    DEFAULT_STYLE,
    STYLE_GUIDES,
    generate_blog_post,
    read_material_files,
)


class BlogWriterGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("키워드 + 자료 → 창의적 블로그 글 생성기")
        self.root.geometry("760x680")

        self.file_paths = []      # 첨부된 자료 파일 경로 목록
        self.generated_text = ""  # 마지막으로 생성된 글

        self._build_widgets()
        self._check_api_key()

    # ---------------- UI 구성 ----------------
    def _build_widgets(self):
        pad = {"padx": 10, "pady": 5}

        # 1) 키워드 입력
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="키워드:").pack(side="left")
        self.keyword_var = tk.StringVar()
        self.keyword_entry = ttk.Entry(top, textvariable=self.keyword_var)
        self.keyword_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # 2) 자료 파일 첨부 영역
        file_frame = ttk.LabelFrame(self.root, text="관련 자료 파일 (txt / pdf)")
        file_frame.pack(fill="both", expand=False, **pad)

        btn_row = ttk.Frame(file_frame)
        btn_row.pack(fill="x", padx=8, pady=6)
        ttk.Button(btn_row, text="파일 첨부", command=self.add_files).pack(side="left")
        ttk.Button(btn_row, text="선택 삭제", command=self.remove_selected).pack(side="left", padx=6)
        ttk.Button(btn_row, text="전체 삭제", command=self.clear_files).pack(side="left")

        self.file_listbox = tk.Listbox(file_frame, height=5, selectmode="extended")
        self.file_listbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # 2-1) 글쓴이 관점 입력 영역 (200자 내외)
        vp_frame = ttk.LabelFrame(self.root, text="나의 관점 (200자 내외, 선택)")
        vp_frame.pack(fill="x", **pad)
        self.viewpoint_text = tk.Text(vp_frame, height=3, wrap="word", font=("맑은 고딕", 10))
        self.viewpoint_text.pack(fill="x", expand=True, padx=8, pady=(6, 2))
        self.vp_count_var = tk.StringVar(value="0 / 200자")
        ttk.Label(vp_frame, textvariable=self.vp_count_var, foreground="gray").pack(
            anchor="e", padx=8, pady=(0, 6)
        )
        self.viewpoint_text.bind("<KeyRelease>", self._update_vp_count)

        # 2-2) 글 스타일 선택 영역 (친근하게 / 진지하게)
        style_frame = ttk.LabelFrame(self.root, text="글 스타일")
        style_frame.pack(fill="x", **pad)
        self.style_var = tk.StringVar(value=DEFAULT_STYLE)
        for name in STYLE_GUIDES:
            ttk.Radiobutton(
                style_frame, text=name, value=name, variable=self.style_var
            ).pack(side="left", padx=8, pady=6)

        # 3) 생성 버튼 + 상태 표시
        action = ttk.Frame(self.root)
        action.pack(fill="x", **pad)
        self.generate_btn = ttk.Button(
            action, text="블로그 글 생성", command=self.on_generate
        )
        self.generate_btn.pack(side="left")
        self.save_btn = ttk.Button(
            action, text="저장(.md)", command=self.save_result, state="disabled"
        )
        self.save_btn.pack(side="left", padx=6)
        self.reset_btn = ttk.Button(action, text="초기화", command=self.reset_all)
        self.reset_btn.pack(side="left", padx=6)

        self.status_var = tk.StringVar(value=f"준비됨 (모델: {DEFAULT_MODEL})")
        ttk.Label(action, textvariable=self.status_var, foreground="gray").pack(
            side="left", padx=10
        )
        self.progress = ttk.Progressbar(action, mode="indeterminate", length=120)
        self.progress.pack(side="right")

        # 4) 결과 출력 영역
        out_frame = ttk.LabelFrame(self.root, text="생성된 블로그 글")
        out_frame.pack(fill="both", expand=True, **pad)
        self.output = scrolledtext.ScrolledText(out_frame, wrap="word", font=("맑은 고딕", 10))
        self.output.pack(fill="both", expand=True, padx=8, pady=8)

    def _check_api_key(self):
        if not (os.getenv("OPENAI_API_KEY") or "").strip():
            messagebox.showwarning(
                "API 키 없음",
                "환경변수 OPENAI_API_KEY 가 설정되어 있지 않습니다.\n"
                '터미널에서 다음을 실행한 뒤 다시 시작하세요:\n\n'
                '  $env:OPENAI_API_KEY = "sk-..."',
            )

    # ---------------- 파일 관리 ----------------
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="자료 파일 선택 (txt / pdf)",
            filetypes=[
                ("지원 문서", "*.txt *.pdf *.md"),
                ("텍스트 파일", "*.txt *.md"),
                ("PDF 파일", "*.pdf"),
                ("모든 파일", "*.*"),
            ],
        )
        for p in paths:
            if p not in self.file_paths:
                self.file_paths.append(p)
                self.file_listbox.insert("end", os.path.basename(p))

    def remove_selected(self):
        for idx in reversed(self.file_listbox.curselection()):
            self.file_listbox.delete(idx)
            del self.file_paths[idx]

    def clear_files(self):
        self.file_listbox.delete(0, "end")
        self.file_paths.clear()

    # ---------------- 관점 글자 수 표시 ----------------
    def _update_vp_count(self, event=None):
        text = self.viewpoint_text.get("1.0", "end-1c")
        n = len(text)
        self.vp_count_var.set(f"{n} / 200자")

    # ---------------- 글 생성 ----------------
    def on_generate(self):
        keyword = self.keyword_var.get().strip()
        if not keyword:
            messagebox.showinfo("입력 필요", "키워드를 입력해 주세요.")
            return
        if not (os.getenv("OPENAI_API_KEY") or "").strip():
            messagebox.showwarning("API 키 없음", "환경변수 OPENAI_API_KEY 를 설정해 주세요.")
            return

        viewpoint = self.viewpoint_text.get("1.0", "end-1c").strip()
        if len(viewpoint) > 300:
            if not messagebox.askyesno(
                "관점이 깁니다",
                f"입력한 관점이 {len(viewpoint)}자입니다. 200자 내외를 권장합니다.\n"
                "이대로 진행할까요?",
            ):
                return

        style = self.style_var.get()

        # 버튼 잠그고 진행 표시
        self.generate_btn.config(state="disabled")
        self.save_btn.config(state="disabled")
        self.progress.start(12)
        self.status_var.set("자료 읽는 중...")
        self.output.delete("1.0", "end")

        # API 호출은 시간이 걸리므로 별도 스레드에서 실행 (UI 멈춤 방지)
        threading.Thread(
            target=self._worker,
            args=(keyword, list(self.file_paths), viewpoint, style),
            daemon=True,
        ).start()

    def _worker(self, keyword, paths, viewpoint, style):
        try:
            material, loaded = read_material_files(paths)
            self._set_status(
                f"글 생성 중... ([{style}] 자료 {len(loaded)}개, 모델: {DEFAULT_MODEL})"
            )
            post = generate_blog_post(keyword, material, viewpoint, style)
            self.root.after(0, self._on_success, post, loaded, style)
        except Exception as e:
            self.root.after(0, self._on_error, str(e))

    def _set_status(self, text):
        self.root.after(0, self.status_var.set, text)

    def _on_success(self, post, loaded, style):
        self.generated_text = post
        self.output.insert("1.0", post)
        self.progress.stop()
        mat = f"자료 {len(loaded)}개 반영" if loaded else "자료 없음"
        self.status_var.set(f"완료 — [{style}] {mat}")
        self.generate_btn.config(state="normal")
        self.save_btn.config(state="normal")

    def _on_error(self, msg):
        self.progress.stop()
        self.status_var.set("오류 발생")
        self.generate_btn.config(state="normal")
        messagebox.showerror("글 생성 오류", f"문제가 발생했습니다:\n{msg}")

    # ---------------- 초기화 ----------------
    def reset_all(self):
        """입력과 결과를 모두 처음 상태로 되돌린다."""
        if self.generated_text or self.keyword_var.get().strip() or self.file_paths:
            if not messagebox.askyesno("초기화", "입력 내용과 생성된 글을 모두 지울까요?"):
                return
        self.keyword_var.set("")
        self.clear_files()
        self.viewpoint_text.delete("1.0", "end")
        self._update_vp_count()
        self.style_var.set(DEFAULT_STYLE)
        self.output.delete("1.0", "end")
        self.generated_text = ""
        self.save_btn.config(state="disabled")
        self.status_var.set(f"준비됨 (모델: {DEFAULT_MODEL})")

    # ---------------- 저장 ----------------
    def save_result(self):
        if not self.generated_text:
            return
        keyword = self.keyword_var.get().strip() or "post"
        safe = "".join(c for c in keyword if c.isalnum() or c in " _-").strip()
        path = filedialog.asksaveasfilename(
            title="블로그 글 저장",
            defaultextension=".md",
            initialfile=f"blog_{safe or 'post'}.md",
            filetypes=[("Markdown", "*.md"), ("텍스트", "*.txt")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.generated_text)
        messagebox.showinfo("저장 완료", f"저장되었습니다:\n{path}")


def main():
    root = tk.Tk()
    BlogWriterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
