import os
import subprocess
import requests
import json
import time
from PIL import Image
from google import genai
from google.genai import types

# ==========================================
# 1. ENVIRONMENT VARIABLES & SETUP
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

CAPTION_PROMPT_ID = "1p_aA4Ga3MScrd_M8rIlfcPcPgSPmjuUd"
THEME_BACKGROUNDS_FOLDER_ID = "1mDj_Tcp1iVD45AXvaaiEAkW96RwmeMcz"

DRIVE_TOKEN = os.environ.get("DRIVE_TOKEN")
STUDENT_NAME = os.environ.get("STUDENT_NAME", "Student").strip()
GRADE_LEVEL = os.environ.get("GRADE_LEVEL", "Grade 1").strip()
THEME = os.environ.get("THEME", "default").lower().strip()
FILE_NAME = os.environ.get("FILE_NAME", "").strip()
WEB_APP_URL = os.environ.get("WEB_APP_URL", "").strip()

RAW_UPLOADS_FOLDER_ID = "1OU5MiRFWGWLoU3xxW5-VfVFnzamAmObY"
FINISHED_VIDEOS_FOLDER_ID = "1KjjL1O4LzSno5uELcgVQRQ_Otj4tW-io"
BRANDING_FOLDER_ID = "1U94j4vyMRnNgCes5Wuo4T0PhdkdW5iI4"

headers = {"Authorization": f"Bearer {DRIVE_TOKEN}", "Accept": "application/json"}

def log(msg):
    print(msg, flush=True)

# ==========================================
# 2. GOOGLE DRIVE API HELPERS
# ==========================================
def search_drive_file(name, parent_id):
    query = f"'{parent_id}' in parents and name contains '{name}' and trashed=false"
    url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id, name, mimeType)"
    res = requests.get(url, headers=headers).json()
    files = res.get("files", [])
    return files[0]["id"] if files else None

def get_first_image_in_folder(folder_id):
    query = f"'{folder_id}' in parents and mimeType contains 'image/' and trashed=false"
    url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id)"
    res = requests.get(url, headers=headers).json()
    files = res.get("files", [])
    return files[0]["id"] if files else None

def get_theme_background_file_id(theme_name, folder_id):
    folder_id_match = search_drive_file(theme_name, folder_id)
    if folder_id_match:
        url = f"https://www.googleapis.com/drive/v3/files/{folder_id_match}?fields=id,mimeType"
        meta = requests.get(url, headers=headers).json()
        if meta.get("mimeType") == "application/vnd.google-apps.folder":
            img_id = get_first_image_in_folder(folder_id_match)
            if img_id: return img_id
        else:
            return folder_id_match

    default_id = search_drive_file("default", folder_id)
    if default_id:
        url = f"https://www.googleapis.com/drive/v3/files/{default_id}?fields=id,mimeType"
        meta = requests.get(url, headers=headers).json()
        if meta.get("mimeType") == "application/vnd.google-apps.folder":
            img_id = get_first_image_in_folder(default_id)
            if img_id: return img_id
        else:
            return default_id
    return None

def download_file(file_id, dest_path):
    log(f"⬇️ Downloading media to {dest_path}...")
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    res = requests.get(url, headers=headers, stream=True)
    if res.status_code == 200:
        with open(dest_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=65536):
                if chunk: f.write(chunk)
        return True
    log(f"⚠️ Failed to download file ID {file_id}: Status {res.status_code}")
    return False

def download_google_doc_text(file_id):
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export?mimeType=text/plain"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.text
    return "Please write an encouraging social media caption."

# ==========================================
# 3. GEMINI AI EVALUATION (THE PROXY BYPASS)
# ==========================================
def evaluate_video(video_path):
    log("🧠 Starting Gemini AI Evaluation...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    proxy_path = "ai_proxy.mp4"
    log("🗜️ Compressing proxy video to bypass Google File API limits...")
    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-t", "180",
        "-vf", "scale=640:-2", "-vcodec", "libx264", "-crf", "32", 
        "-preset", "ultrafast", "-acodec", "aac", "-b:a", "48k", 
        proxy_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        with open(proxy_path, "rb") as f:
            video_bytes = f.read()
        log(f"📦 Proxy video ready: {len(video_bytes) / (1024*1024):.2f} MB")
        video_part = types.Part.from_bytes(data=video_bytes, mime_type='video/mp4')
    except Exception as e:
        log(f"❌ Failed to process proxy video: {e}")
        return {}

    rubrics = {
        "1": "body action, body posture, speaking clarity",
        "2": "body action, body posture, speaking clarity, eye contact, intonation, energy, action demonstration",
        "3": "body action, body posture, speaking clarity, eye contact, intonation, energy, action demonstration, fluency, props, self-explaination, role play and application sharing",
        "4": "body action, body posture, speaking clarity, eye contact, intonation, energy, action demonstration, fluency, props, self-explaination, role play, application sharing, voice character and facial expression",
        "5": "body action, body posture, speaking clarity, eye contact, intonation, energy, action demonstration, fluency, props, self-explaination, role play, application sharing, voice character, facial expression and audience engagement",
        "6": "body action, body posture, speaking clarity, eye contact, intonation, energy, action demonstration, fluency, props, self-explaination, role play, application sharing, voice character, facial expression, audience engagement and x-factor"
    }
    
    grade_num = "".join(filter(str.isdigit, GRADE_LEVEL)) or "1"
    current_rubric = rubrics.get(grade_num, rubrics["1"])
    caption_instructions = download_google_doc_text(CAPTION_PROMPT_ID)

    prompt = f"""Role: Expert public speaking evaluator for the Deemcee programme.
Task: Evaluate student speech video for {STUDENT_NAME} ({GRADE_LEVEL}, Theme: "{THEME}").
Rubric: [{current_rubric}].
Scoring: Strictly 1 to 10 for each element with timestamps.

Social Media Instructions:
{caption_instructions}

Respond strictly in valid JSON format matching:
{{
  "encouragingSummary": "Summary text",
  "elements": [ {{ "elementName": "Body Action", "score": 7, "feedback": "Feedback @ 0:15" }} ],
  "totalScore": 21,
  "maxScore": 30,
  "advanceRecommendation": "Yes",
  "actionPlan": ["Tip 1", "Tip 2"],
  "socialMediaCaption": "The full social media text."
}}"""

    models_to_try = ["gemini-3.5-flash-lite", "gemini-3.5-flash"]
    max_retries_per_model = 3
    retry_delay_seconds = 20 

    for model_name in models_to_try:
        log(f"\n🚀 Attempting Model: {model_name}")
        for attempt in range(1, max_retries_per_model + 1):
            try:
                log(f"🤖 Generation Attempt {attempt}/{max_retries_per_model}...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=[video_part, "Watch this video and evaluate the student's performance."],
                    config=types.GenerateContentConfig(
                        system_instruction=prompt,
                        response_mime_type="application/json",
                        temperature=0.2
                    )
                )
                
                evaluation_data = json.loads(response.text)
                log(f"✅ AI Evaluation parsed successfully with {model_name}!")
                return evaluation_data
                
            except Exception as e:
                log(f"⚠️ Attempt {attempt} with {model_name} failed: {str(e)}")
                if attempt < max_retries_per_model:
                    log(f"⏳ Waiting {retry_delay_seconds}s before retry...")
                    time.sleep(retry_delay_seconds)
                else:
                    log(f"❌ Moving to next model fallback...")

    log("🚨 All models failed. Returning empty evaluation.")
    return {}

# ==========================================
# 4. FFMPEG VIDEO PROCESSING
# ==========================================
def get_green_screen_color(video_path):
    log("🔍 Auto-detecting green screen color...")
    subprocess.run(["ffmpeg", "-y", "-ss", "00:00:00.500", "-i", video_path, "-vframes", "1", "sample.png"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        img = Image.open("sample.png").convert("RGB")
        w, h = img.size
        samples = [img.getpixel((int(w*0.05), int(h*0.05))), img.getpixel((int(w*0.95), int(h*0.05)))]
        green_samples = [s for s in samples if s[1] > s[0] and s[1] > s[2]]
        if green_samples:
            avg_r = sum(s[0] for s in green_samples) // len(green_samples)
            avg_g = sum(s[1] for s in green_samples) // len(green_samples)
            avg_b = sum(s[2] for s in green_samples) // len(green_samples)
            return f"0x{avg_r:02X}{avg_g:02X}{avg_b:02X}"
    except Exception:
        pass
    return "0x00B800"

def process_and_upload(raw_video):
    bg_file_id = get_theme_background_file_id(THEME, THEME_BACKGROUNDS_FOLDER_ID)
    has_bg = False
    if bg_file_id and download_file(bg_file_id, "bg.png"):
        has_bg = True
    else:
        log("⚠️ Theme background not found. Creating fallback 1080p backdrop...")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=#1A365D:s=1920x1080:d=1", "-vframes", "1", "bg.png"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        has_bg = True
    
    has_logo = False
    logo_file_id = search_drive_file("logo", BRANDING_FOLDER_ID)
    if logo_file_id and download_file(logo_file_id, "logo.png"):
        has_logo = True

    color = get_green_screen_color(raw_video)
    final_name = f"{STUDENT_NAME}_{THEME}_Final.mp4".replace(" ", "_")
    
    log(f"🎬 Running FFmpeg Chroma Key Pipeline (Background: {has_bg}, Logo: {has_logo})...")
    
    if has_logo:
        filter_complex = (
            "[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30[bg];"
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,chromakey={color}:0.05:0.10,despill=green,format=yuva420p,fps=30[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)[keyed];"
            "[2:v]scale=240:-1,format=yuva420p[logo];"
            "[keyed][logo]overlay=main_w-overlay_w-30:30[v_final]"
        )
        cmd = [
            "ffmpeg", "-y", "-i", raw_video, "-loop", "1", "-i", "bg.png", "-loop", "1", "-i", "logo.png",
            "-filter_complex", filter_complex, "-map", "[v_final]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
            "-shortest", final_name
        ]
    else:
        filter_complex = (
            "[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30[bg];"
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,chromakey={color}:0.05:0.10,despill=green,format=yuva420p,fps=30[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)[v_final]"
        )
        cmd = [
            "ffmpeg", "-y", "-i", raw_video, "-loop", "1", "-i", "bg.png",
            "-filter_complex", filter_complex, "-map", "[v_final]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
            "-shortest", final_name
        ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"❌ FFmpeg error:\n{result.stderr}")
        raise RuntimeError("FFmpeg processing failed.")
    
    log("☁️ Uploading Final Video to Drive...")
    init_res = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
        headers={"Authorization": f"Bearer {DRIVE_TOKEN}", "Content-Type": "application/json"},
        json={"name": final_name, "parents": [FINISHED_VIDEOS_FOLDER_ID]}
    )
    upload_url = init_res.headers["Location"]
    with open(final_name, "rb") as f:
        final_res = requests.put(upload_url, data=f.read())
    
    file_id = final_res.json().get('id')
    video_link = f"https://drive.google.com/file/d/{file_id}/view"
    log(f"🎉 SUCCESS! Final video uploaded with ID: {file_id}")
    return video_link

# ==========================================
# 5. EXECUTION & WEBHOOK BOOMERANG
# ==========================================
if __name__ == "__main__":
    log(f"🚀 Starting Deemcee Pipeline for {STUDENT_NAME}...")
    
    raw_id = search_drive_file(FILE_NAME, RAW_UPLOADS_FOLDER_ID)
    if raw_id and download_file(raw_id, "raw_video.mp4"):
        
        # 1. Run AI Evaluation via Proxy Bypass
        eval_data = evaluate_video("raw_video.mp4")
            
        # 2. Render and Upload Video
        final_video_link = process_and_upload("raw_video.mp4")
        
        # 3. Send Webhook Return to Google Apps Script
        if WEB_APP_URL and eval_data:
            log("📡 Sending completed data back to Apps Script...")
            payload = {
                "action": "evaluationComplete",
                "studentName": STUDENT_NAME,
                "studentGrade": GRADE_LEVEL,
                "speechTheme": THEME,
                "fileName": FILE_NAME,
                "videoLink": final_video_link,
                "evaluation": eval_data
            }
            res = requests.post(WEB_APP_URL, json=payload)
            log(f"✅ Webhook return status: {res.status_code}")
        else:
            log("⚠️ Web App URL missing or Evaluation failed. Skipping return webhook.")
            
    else:
        log("❌ Failed to find or download the raw video.")
