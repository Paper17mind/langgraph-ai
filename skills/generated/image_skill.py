import os
import re
import base64
import mimetypes
import urllib.parse
import requests
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()

def get_cli_ascii_preview(image_path: str, width: int = 45) -> str:
    """Renders ANSI TrueColor pixel preview of an image for CLI terminal display."""
    try:
        if not os.path.exists(image_path):
            return ""
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        new_w = width
        new_h = max(1, int(new_w * (h / w) * 0.45))
        img = img.resize((new_w, new_h))
        
        lines = []
        for y in range(new_h):
            line_str = []
            for x in range(new_w):
                r, g, b = img.getpixel((x, y))
                line_str.append(f"\033[38;2;{r};{g};{b}m█\033[0m")
            lines.append("".join(line_str))
        return "\n" + "\n".join(lines) + "\n"
    except Exception:
        return ""


@tool
def generate_image_tool(prompt: str, filename: str = "data/images/output.png", output_path: str = None, width: int = 600, height: int = 600) -> str:
    """
    Generate a high-quality image from a text prompt and save it to data/images/<filename>.png.
    
    Args:
        prompt (str): Text description of the image to generate.
        filename (str): Output filepath (default: data/images/output.png).
        output_path (str): Alias for filename (default: None).
        width (int): Image width in pixels 
        height (int): Image height in pixels 
    """
    load_dotenv()
    if output_path:
        filename = output_path

    # Enforce directory placement rule
    if not filename.startswith("data/images/"):
        filename = os.path.join("data/images", os.path.basename(filename))
        
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    # Clean local file paths from prompt string to prevent Google Imagen 3 API from stalling
    clean_prompt = re.sub(r'data/images/[\w\.-]+', '', prompt).strip()
    clean_prompt = re.sub(r'logs/[\w\.-]+(/[^\s,]+)?', '', clean_prompt).strip()
    if not clean_prompt:
        clean_prompt = prompt

    # 1. PRIMARY ENGINE: 9Router API
    try:
        print("🎨 [image_generator] Mencoba Primary Engine: 9Router API (estimasi 15-20s)...", flush=True)
        url_base = os.getenv("9ROUTER_URL", "http://localhost:20128/v1/chat/completions").replace("/chat/completions", "")
        key = os.getenv("9ROUTER_API_KEY", "")
        model = 'ag/gemini-3.1-flash-image'
        
        res = requests.post(
            f"{url_base}/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "prompt": clean_prompt, "size": f"{width}x{height}"},
            timeout=25
        )
        if res.status_code == 200:
            img_bytes = None
            try:
                res_json = res.json()
                if "data" in res_json and len(res_json["data"]) > 0:
                    item = res_json["data"][0]
                    if "b64_json" in item:
                        img_bytes = base64.b64decode(item["b64_json"])
                    elif "url" in item:
                        img_res = requests.get(item["url"], timeout=20)
                        if img_res.status_code == 200:
                            img_bytes = img_res.content
            except Exception:
                if len(res.content) > 500 and not res.content.startswith(b"{"):
                    img_bytes = res.content

            if img_bytes:
                with open(filename, "wb") as f:
                    f.write(img_bytes)
                preview = get_cli_ascii_preview(filename)
                return f"✅ Gambar berhasil dibuat (9Router) dan disimpan di: {filename}\n{preview}"
            else:
                print(f"⚠️ [image_generator] 9Router JSON parse failed, status 200 but no image data", flush=True)
        else:
            print(f"⚠️ [image_generator] 9Router status {res.status_code}: {res.text[:150]}", flush=True)
    except Exception as e:
        print(f"⚠️ [image_generator] 9Router primary error: {e}", flush=True)

    # 2. FALLBACK ENGINE: Pollinations AI
    try:
        print("🎨 [image_generator] Mencoba Fallback Engine: Pollinations AI (estimasi 3-5s)...", flush=True)
        encoded_prompt = urllib.parse.quote(prompt)
        pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(pollinations_url, headers=headers, timeout=25)
        if res.status_code == 200 and len(res.content) > 1000:
            with open(filename, "wb") as f:
                f.write(res.content)
            preview = get_cli_ascii_preview(filename)
            return f"✅ Gambar berhasil dibuat (Fallback Engine) dan disimpan di: {filename}\n{preview}"
        else:
            print(f"⚠️ [image_generator] Fallback Pollinations status={res.status_code}", flush=True)
    except Exception as e:
        print(f"⚠️ [image_generator] Fallback Pollinations error: {e}", flush=True)

    return f"❌ Gagal membuat gambar untuk prompt: '{prompt}'"


import io
from PIL import Image

@tool
def analyze_image_tool(image_path: str, prompt: str = "Jelaskan dan analisis gambar ini secara detail dalam Bahasa Indonesia.") -> str:
    """
    Recognize, describe, or analyze an image file (PNG, JPG, WEBP, etc.) using AI Vision capability.
    
    Args:
        image_path (str): Path to the image file (e.g. data/images/output.png).
        prompt (str): Question or instruction for analyzing the image.
    """
    load_dotenv()
    if not os.path.exists(image_path):
        return f"❌ File gambar '{image_path}' tidak ditemukan."
        
    try:
        # 1. Optimize/Resize image with PIL for Vision API
        img = Image.open(image_path)
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"[analyze_image_tool] Image load error: {e}")
        return f"❌ Gagal membaca atau memproses berkas gambar '{image_path}'."
        
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"}}
                ]
            }
        ]
    }
    
    # Primary: 9Router API
    try:
        url_base = os.getenv("9ROUTER_URL", "http://localhost:20128/v1/chat/completions")
        key_9r = os.getenv("9ROUTER_API_KEY", "")
        model_9r = os.getenv("9ROUTER_MODEL", "antigravity")
        
        req_payload = dict(payload)
        req_payload["model"] = model_9r
        res = requests.post(
            url_base,
            headers={"Authorization": f"Bearer {key_9r}", "Content-Type": "application/json"},
            json=req_payload,
            timeout=45
        )
        if res.status_code == 200:
            analysis = res.json()["choices"][0]["message"]["content"]
            return f"🔍 Hasil Analisis Gambar ({image_path}) [9Router]:\n\n{analysis}"
        else:
            print(f"⚠️ [analyze_image_tool] 9Router error {res.status_code}: {res.text[:150]}")
    except Exception as e:
        print(f"⚠️ [analyze_image_tool] 9Router Primary error: {e}")

    # Fallback: Groq Vision API
    try:
        print("🔍 [analyze_image_tool] Mencoba Fallback Engine: Groq Vision...")
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            req_payload = dict(payload)
            req_payload["model"] = "qwen/qwen3.6-27b"
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json=req_payload,
                timeout=45
            )
            if res.status_code == 200:
                analysis = res.json()["choices"][0]["message"]["content"]
                # Clean thinking tokens if present
                if "</think>" in analysis:
                    analysis = analysis.split("</think>")[-1].strip()
                return f"🔍 Hasil Analisis Gambar ({image_path}) [Groq Vision]:\n\n{analysis}"
            else:
                print(f"⚠️ [analyze_image_tool] Groq status {res.status_code}: {res.text[:150]}")
    except Exception as e:
        print(f"⚠️ [analyze_image_tool] Groq Fallback error: {e}")

    return f"❌ Gagal menganalisis gambar '{image_path}'."
