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
# 2. GOOGLE DRIVE API HELPERS (BULLETPROOF SEARCH)
# ==========================================
def get_all_files_in_folder(folder_id):
    """Fetches all files in a folder to do reliable local string matching."""
    query = f"'{folder_id}' in parents and trashed=false"
    url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id, name, mimeType)"
    res = requests.get(url, headers=headers).json()
    return res.get("files", [])

def search_drive_file(keyword, folder_id, is_folder=False):
    """Case-insensitive search across all files in a specific folder."""
    files = get_all_files_in_folder(folder_id)
    keyword_lower = keyword.lower()
    for f in files:
        if keyword_lower in f.get("name", "").lower():
            if is_folder and f.get("mimeType") != "application/vnd.google-apps.folder":
                continue
            return f["id"]
    return None

def get_first_image_in_folder(folder_id):
    files = get_all_files_in_folder(folder_id)
    for f in files:
        if "image/" in f.get("mimeType", ""):
            return f["id"]
    return None

def get_theme_background_file_id(theme_name, folder_id):
    log(f"🔍 Searching for '{theme_name}' background folder...")
    folder_id_match = search_drive_file(theme_name, folder_id, is_folder=True)
    
    if folder_id_match:
        img_id = get_first_image_in_folder(folder_id_match)
        if img_id: return img_id

    log("⚠️ Theme folder not found. Falling back to default...")
    default_id = search_drive_file("default", folder_id, is_folder=True)
    if default_id:
        img_id = get_first_image_in_folder(default_id)
        if img_id: return img_id
        
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
# 3. GEMINI AI EVALUATION
# ==========================================
def evaluate_video(video_path):
    log("🧠 Starting Gemini AI Evaluation...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    proxy_path = "ai_proxy.mp4"
    log("🗜️ Compressing proxy video to bypass Google File API limits...")
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path, "-t", "180",
        "-vf", "scale=640:-2", "-vcodec", "libx264", "-crf", "32", 
        "-preset", "ultrafast", "-acodec", "aac", "-b:a", "48k", proxy_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        with open(proxy_path, "rb") as f:
            video_bytes = f.read()
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
    for model_name in models_to_try:
        log(f"\n🚀 Attempting Model: {model_name}")
        for attempt in range(1, 4):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[video_part, "Watch this video and evaluate the student's performance."],
                    config=types.GenerateContentConfig(
                        system_instruction=prompt,
                        response_mime_type="application/json",
                        temperature=0.2
                    )
                )
                eval_data = json.loads(response.text)
                log(f"✅ AI Evaluation parsed successfully!")
                return eval_data
            except Exception as e:
                log(f"⚠️ Attempt {attempt} failed. Retrying...")
                time.sleep(20)

    log("🚨 All models failed. Returning empty evaluation.")
    return {}

# ==========================================
# 4. FFMPEG VIDEO PROCESSING (WITH INTRO/OUTRO)
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

def sanitize_and_normalize(has_bg, has_logo, has_intro, has_outro):
    log("🧼 Sanitizing images & normalizing videos for FFmpeg...")
    if has_bg:
        subprocess.run(["ffmpeg", "-y", "-i", "bg.png", "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=rgb24", "-vframes", "1", "clean_bg.png"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if has_logo:
        subprocess.run(["ffmpeg", "-y", "-i", "logo.png", "-vf", "scale=240:-1,format=rgba", "-vframes", "1", "clean_logo.png"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Normalize intro/outro to exactly 1920x1080, 30fps, AAC audio to prevent concat crashes
    norm_cmd = ["-vf", "scale=1920:1080,setsar=1", "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-r", "30"]
    if has_intro:
        subprocess.run(["ffmpeg", "-y", "-i", "intro.mp4"] + norm_cmd + ["intro_norm.mp4"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if has_outro:
        subprocess.run(["ffmpeg", "-y", "-i", "outro.mp4"] + norm_cmd + ["outro_norm.mp4"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def process_and_upload(raw_video):
    # 1. Download Assets
    bg_file_id = get_theme_background_file_id(THEME, THEME_BACKGROUNDS_FOLDER_ID)
    has_bg = download_file(bg_file_id, "bg.png") if bg_file_id else False
    if not has_bg:
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=#1A365D:s=1920x1080:d=1", "-vframes", "1", "bg.png"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        has_bg = True

    logo_id = search_drive_file("logo", BRANDING_FOLDER_ID)
    intro_id = search_drive_file("intro", BRANDING_FOLDER_ID)
    outro_id = search_drive_file("outro", BRANDING_FOLDER_ID)

    has_logo = download_file(logo_id, "logo.png") if logo_id else False
    has_intro = download_file(intro_id, "intro.mp4") if intro_id else False
    has_outro = download_file(outro_id, "outro.mp4") if outro_id else False

    # 2. Sanitize to RGB/RGBA & Normalize
    sanitize_and_normalize(has_bg, has_logo, has_intro, has_outro)
    color = get_green_screen_color(raw_video)

    # 3. Render Main Speech Body
    log(f"🎬 Rendering Main Speech (Background: {has_bg}, Logo: {has_logo})...")
    if has_logo:
        filter_complex = (
            "[1:v]scale=1920:1080,setsar=1[bg];"
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,chromakey={color}:0.05:0.10,despill=green,format=yuva420p,fps=30[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)[keyed];"
            "[2:v]format=rgba[logo];"
            "[keyed][logo]overlay=main_w-overlay_w-30:30[v_final]"
        )
        cmd = ["ffmpeg", "-y", "-i", raw_video, "-loop", "1", "-i", "clean_bg.png", "-loop", "1", "-i", "clean_logo.png", "-filter_complex", filter_complex, "-map", "[v_final]", "-map", "0:a?", "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-r", "30", "-shortest", "main_processed.mp4"]
    else:
        filter_complex = (
            "[1:v]scale=1920:1080,setsar=1[bg];"
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,chromakey={color}:0.05:0.10,despill=green,format=yuva420p,fps=30[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)[v_final]"
        )
        cmd = ["ffmpeg", "-y", "-i", raw_video, "-loop", "1", "-i", "clean_bg.png", "-filter_complex", filter_complex, "-map", "[v_final]", "-map", "0:a?", "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-r", "30", "-shortest", "main_processed.mp4"]
    
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 4. Concatenate Intro + Main + Outro
    log("🎞️ Stitching Intro, Main Body, and Outro together...")
    with open("concat_list.txt", "w") as f:
        if has_intro: f.write("file 'intro_norm.mp4'\n")
        f.write("file 'main_processed.mp4'\n")
        if has_outro: f.write("file 'outro_norm.mp4'\n")

    final_name = f"{STUDENT_NAME}_{THEME}_Final.mp4".replace(" ", "_")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat_list.txt", "-c", "copy", final_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 5. Upload Final
    log("☁️ Uploading Complete Deliverable to Drive...")
    init_res = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
        headers={"Authorization": f"Bearer {DRIVE_TOKEN}", "Content-Type": "application/json"},
        json={"name": final_name, "parents": [FINISHED_VIDEOS_FOLDER_ID]}
    )
    upload_url = init_res.headers["Location"]
    with open(final_name, "rb") as f:
        final_res = requests.put(upload_url, data=f.read())
    
    file_id = final_res.json().get('id')
    return f"https://drive.google.com/file/d/{file_id}/view"

# ==========================================
# 5. EXECUTION
# ==========================================
if __name__ == "__main__":
    log(f"🚀 Starting Deemcee Pipeline for {STUDENT_NAME}...")
    
    raw_id = search_drive_file(FILE_NAME, RAW_UPLOADS_FOLDER_ID)
    if raw_id and download_file(raw_id, "raw_video.mp4"):
        
        eval_data = evaluate_video("raw_video.mp4")
        final_video_link = process_and_upload("raw_video.mp4")
        
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
            requests.post(WEB_APP_URL, json=payload)
            log("✅ Webhook return successful.")
    else:
        log("❌ Failed to find or download the raw video.")
