#!/usr/bin/env python3
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

API_URL = "http://localhost:20128/v1/chat/completions"
API_KEY = "sk-a5be1fc2a203d8a3-q7rbod-9d98d295"
MODEL = "ag/gemini-3.8-flash-low"

SYSTEM_PROMPT = """You are an expert translator specializing in algorithms, data structures, competitive programming (IOI, ICPC), and LaTeX documentation.
Translate English LaTeX content into fluent, idiomatic, technical Persian.

Rules:
1. Preserve all LaTeX tags, environments, commands, math expressions ($...$, \\[...\\]), labels, references, index markers, citations, and table formatting exactly.
2. Inside \\begin{lstlisting} ... \\end{lstlisting}, preserve all C++ code, headers, keywords, syntax, and comments intact (comments may be translated to Persian if straightforward, but leave code syntax 100% exact).
3. In \\begin{tikzpicture} ... \\end{tikzpicture}, preserve all coordinates, node names, and formatting; translate only visible human labels inside nodes if applicable.
4. Translate section titles, key phrases, and explanatory text accurately into standard Persian computer science terminology:
   - Competitive programming: برنامه‌نویسی رقابتی
   - Data structures: ساختمان داده‌ها / داده‌ساختارها
   - Time complexity: پیچیدگی زمانی
   - Dynamic programming: برنامه‌نویسی پویا
   - Greedy algorithm: الگوریتم حریصانه
   - Complete search: جستجوی کامل
   - Graph: گراف
   - Tree: درخت
5. ZERO em-dash (—). Never use the em-dash character.
6. Output ONLY the raw translated LaTeX snippet. Do NOT include markdown code fences (```latex or ```)."""


def call_llm(prompt: str, retries: int = 5) -> str:
    payload = json.dumps({
        "model": MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
    )

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
                res = ""
                if "data: " in raw:
                    for line in raw.splitlines():
                        line = line.strip()
                        if line.startswith("data: ") and not line.endswith("[DONE]"):
                            try:
                                d = json.loads(line[6:])
                                delta = d.get("choices", [{}])[0].get("delta", {})
                                res += delta.get("content", "")
                            except Exception:
                                pass
                else:
                    data = json.loads(raw)
                    res = data["choices"][0]["message"]["content"]

                res = re.sub(r"^```(?:latex)?\s*\n", "", res, flags=re.MULTILINE)
                res = re.sub(r"\n```\s*$", "", res, flags=re.MULTILINE)
                res = res.replace("—", " - ")
                return res
        except Exception as e:
            if attempt == retries - 1:
                print(f"Error calling LLM after {retries} retries: {e}", file=sys.stderr)
                raise
            time.sleep(2 * (attempt + 1))
    return ""


def split_into_chunks(text: str, max_chunk_size: int = 3000) -> list[str]:
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_len = 0
    in_code_block = False

    for p in paragraphs:
        if "\\begin{lstlisting}" in p:
            in_code_block = True
        if "\\end{lstlisting}" in p:
            in_code_block = False

        p_len = len(p) + 2
        if current_len + p_len > max_chunk_size and current_chunk and not in_code_block:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [p]
            current_len = p_len
        else:
            current_chunk.append(p)
            current_len += p_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def translate_file(file_path: str):
    backup_path = file_path + ".orig"
    if os.path.exists(backup_path):
        print(f"[{os.path.basename(file_path)}] Already translated (backup exists), skipping.")
        return

    print(f"[{os.path.basename(file_path)}] Translating...")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    chunks = split_into_chunks(content)
    total_chunks = len(chunks)
    print(f"[{os.path.basename(file_path)}] Total chunks: {total_chunks}")

    translated_chunks: list[str] = [""] * total_chunks

    def translate_chunk(idx, text):
        trans = call_llm(text)
        return idx, trans

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(translate_chunk, i, chunk): i for i, chunk in enumerate(chunks)}
        for future in concurrent.futures.as_completed(futures):
            idx, res = future.result()
            translated_chunks[idx] = res
            print(f"[{os.path.basename(file_path)}] Finished chunk {idx+1}/{total_chunks}")

    result = "\n\n".join(translated_chunks)

    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"[{os.path.basename(file_path)}] Completed and saved.")

    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fn = os.path.basename(file_path)
        subprocess.run(["git", "-C", base_dir, "add", fn], check=True)
        subprocess.run(["git", "-C", base_dir, "commit", "-m", f"feat: translate {fn} to persian"], check=True)
        subprocess.run(["git", "-C", base_dir, "push", "origin", "master"], check=True)
        print(f"[{os.path.basename(file_path)}] Committed and pushed to GitHub.")
    except Exception as e:
        print(f"Git commit/push error: {e}", file=sys.stderr)


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_files = [f"chapter{i:02d}.tex" for i in range(4, 31)] + ["list.tex"]

    for fn in target_files:
        fp = os.path.join(base_dir, fn)
        if os.path.exists(fp):
            translate_file(fp)
