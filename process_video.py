import os
import subprocess
import requests
import json
import time
import sys
from PIL import Image
from google import genai
from google.genai import types

# ==========================================
# 1. ENVIRONMENT VARIABLES & SETUP
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

CAPTION_PROMPT_ID = "1p_aA4Ga3MScrd_M8rIlfcPcPgSPmjuUd"
THEME_BACKGROUNDS_FOLDER_ID = "1mDj_Tcp1iVD45AXvaaiEAkW96RwmeMcz"
BRANDING_FOLDER_ID = "1Yi8ttLH0hx92VEKQ98CgNHI8jGWh7MpX"
RAW_UPLOADS_FOLDER_ID = "1OU5MiRFWGWLoU3xxW5-VfVFnzamAmObY"
FINISHED_FOLDER_ID = "1yZ374vWosaiBwCp3RiWq1IjsVW7sDJAr"

DRIVE_TOKEN = os.environ.get("DRIVE_TOKEN")
STUDENT_NAME = os.environ.get("STUDENT_NAME", "Student").strip()
GRADE_LEVEL = os.environ.get("GRADE_LEVEL", "Grade 1").strip()
THEME = os.environ.get("THEME", "default").lower().strip()
FILE_NAME = os.environ.get("FILE_NAME", "").strip()
WEB_APP_URL = os.environ.get("WEB_APP_URL", "").strip()

headers = {"Authorization": f"Bearer {DRIVE_TOKEN}", "Accept": "application/json"}

def log(msg):
    print(msg, flush=True)

# ==========================================
# 2. GOOGLE DRIVE API HELPERS
# ==========================================
def get_all_files_in_folder(folder_id):
    query = f"'{folder_id}' in parents and trashed=false"
    url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id, name, mimeType)"
    res = requests.get(url, headers=headers).json()
    return res.get("files", [])

def search_drive_file(keyword, folder_id, is_folder=False):
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
    if not file_id: return False
    log(f"⬇️ Downloading {dest_path} via Drive API (ID: {file_id})...")
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    res = requests.get(url, headers=headers, stream=True)
    if res.status_code == 200:
        with open(dest_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=65536):
                if chunk: f.write(chunk)
        return True
    return False

def download_google_doc_text(file_id):
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export?mimeType=text/plain"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.text
    return "Please write an encouraging social media caption."

# ==========================================
# 3. AUTO-DETECT GREEN SCREEN COLOR
# ==========================================
def auto_detect_greenscreen_color(video_path):
    log("🔍 Analyzing video to auto-detect exact green screen color...")
    try:
        subprocess.run(["ffmpeg", "-y", "-ss", "00:00:00.500", "-i", video_path, "-vframes", "1", "sample_frame.png"], capture_output=True)
        img = Image.open("sample_frame.png").convert("RGB")
        w, h = img.size
        sample_points = [(int(w * 0.05), int(h * 0.05)), (int(w * 0.95), int(h * 0.05)), (int(w * 0.05), int(h * 0.20)), (int(w * 0.95), int(h * 0.20))]
        green_samples = [img.getpixel((x, y)) for x, y in sample_points if img.getpixel((x, y))[1] > img.getpixel((x, y))[0] and img.getpixel((x, y))[1] > img.getpixel((x, y))[2]]

        if green_samples:
            avg_r = int(sum(s[0] for s in green_samples) / len(green_samples))
            avg_g = int(sum(s[1] for s in green_samples) / len(green_samples))
            avg_b = int(sum(s[2] for s in green_samples) / len(green_samples))
            detected_hex = f"0x{avg_r:02X}{avg_g:02X}{avg_b:02X}"
            log(f"🎯 Auto-Detected Green Screen Color: {detected_hex}")
            return detected_hex
    except Exception:
        pass
    log("⚠️ No dominant green detected in corners, fallback to 0x00B800")
    return "0x00B800"

# ==========================================
# 4. SANITIZE & NORMALIZE
# ==========================================
def sanitize_images():
    has_clean_bg, has_clean_logo = False, False
    if os.path.exists("bg.png") and os.path.getsize("bg.png") > 1024:
        log("🧼 Sanitizing Background to 16:9 RGB24...")
        res = subprocess.run(["ffmpeg", "-y", "-i", "bg.png", "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=rgb24", "-vframes", "1", "clean_bg.png"], capture_output=True)
        if res.returncode == 0: has_clean_bg = True

    if os.path.exists("logo.png") and os.path.getsize("logo.png") > 1024:
        log("🧼 Sanitizing Deemcee Logo to RGBA PNG...")
        res = subprocess.run(["ffmpeg", "-y", "-i", "logo.png", "-vf", "scale=240:-1,format=rgba", "-vframes", "1", "clean_logo.png"], capture_output=True)
        if res.returncode == 0: has_clean_logo = True
    return has_clean_bg, has_clean_logo

def normalize_clip(input_path, output_path, step_name):
    log(f"🎬 Normalizing {step_name} ({input_path})...")
    subprocess.run(["ffmpeg", "-y", "-i", input_path, "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k", output_path], capture_output=True)

# ==========================================
# 5. GEMINI AI EVALUATION
# ==========================================
def evaluate_video(video_path):
    log("🧠 Starting Gemini AI Evaluation...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    proxy_path = "ai_proxy.mp4"
    log("🗜️ Compressing proxy video to bypass Google File API limits...")
    subprocess.run(["ffmpeg", "-y", "-i", video_path, "-t", "180", "-vf", "scale=640:-2", "-vcodec", "libx264", "-crf", "32", "-preset", "ultrafast", "-acodec", "aac", "-b:a", "48k", proxy_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        with open(proxy_path, "rb") as f: video_bytes = f.read()
        video_part = types.Part.from_bytes(data=video_bytes, mime_type='video/mp4')
    except Exception: return {}

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
                    config=types.GenerateContentConfig(system_instruction=prompt, response_mime_type="application/json", temperature=0.2)
                )
                eval_data = json.loads(response.text)
                log(f"✅ AI Evaluation parsed successfully!")
                return eval_data
            except Exception:
                time.sleep(20)
    return {}

# ==========================================
# 6. MAIN COMPOSITOR PIPELINE
# ==========================================
def process_video():
    log("=====================================================")
    log("📥 STEP 1: DOWNLOADING REQUIRED ASSETS")
    
    bg_file_id = get_theme_background_file_id(THEME, THEME_BACKGROUNDS_FOLDER_ID)
    has_bg = download_file(bg_file_id, "bg.png") if bg_file_id else False
    if not has_bg:
        log("⚠️ No background found. Generating fallback blue canvas...")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=#1A365D:s=1920x1080:d=1", "-vframes", "1", "bg.png"], capture_output=True)
        has_bg = True

    has_logo = download_file(search_drive_file("logo", BRANDING_FOLDER_ID), "logo.png")
    has_intro = download_file(search_drive_file("intro", BRANDING_FOLDER_ID), "intro.mp4")
    has_outro = download_file(search_drive_file("outro", BRANDING_FOLDER_ID), "outro.mp4")

    log("=====================================================")
    log("🧹 STEP 2: SANITIZATION & PREP")
    detected_color = auto_detect_greenscreen_color("raw_input.mp4")
    has_clean_bg, has_clean_logo = sanitize_images()
    temp_keyed = "temp_keyed.mp4"

    log("=====================================================")
    log("🎬 STEP 3: CHROMA KEY & BRANDING")
    if has_clean_bg and has_clean_logo:
        filter_complex = f"[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30[bg];[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,chromakey={detected_color}:0.05:0.10,despill=green,format=yuva420p,fps=30[fg];[bg][fg]overlay=(W-w)/2:(H-h)[keyed];[2:v]scale=240:-1,format=yuva420p[logo];[keyed][logo]overlay=main_w-overlay_w-30:30[v_final]"
        cmd1 = ["ffmpeg", "-y", "-i", "raw_input.mp4", "-loop", "1", "-i", "clean_bg.png", "-loop", "1", "-i", "clean_logo.png", "-filter_complex", filter_complex, "-map", "[v_final]", "-map", "0:a?", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k", "-shortest", temp_keyed]
    elif has_clean_bg:
        filter_complex = f"[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30[bg];[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,chromakey={detected_color}:0.05:0.10,despill=green,format=yuva420p,fps=30[fg];[bg][fg]overlay=(W-w)/2:(H-h)[v_final]"
        cmd1 = ["ffmpeg", "-y", "-i", "raw_input.mp4", "-loop", "1", "-i", "clean_bg.png", "-filter_complex", filter_complex, "-map", "[v_final]", "-map", "0:a?", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k", "-shortest", temp_keyed]
    else:
        cmd1 = ["ffmpeg", "-y", "-i", "raw_input.mp4", "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-ar", "44100", "-ac", "2", temp_keyed]
    
    subprocess.run(cmd1, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("✅ Chroma Key Render Complete.")

    log("=====================================================")
    log("🎞️ STEP 4: CONCATENATING INTRO / OUTRO")
    final_name = f"{STUDENT_NAME}_{THEME}_Final.mp4".replace(" ", "_")
    if has_intro or has_outro:
        with open("concat_list.txt", "w") as f:
            if has_intro: 
                normalize_clip("intro.mp4", "norm_intro.mp4", "Intro Video")
                f.write("file 'norm_intro.mp4'\n")
            f.write(f"file '{temp_keyed}'\n")
            if has_outro: 
                normalize_clip("outro.mp4", "norm_outro.mp4", "Outro Video")
                f.write("file 'norm_outro.mp4'\n")

        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat_list.txt", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", final_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        os.rename(temp_keyed, final_name)
    log("✅ Final Video Stitched.")

    log("=====================================================")
    log(f"☁️ STEP 5: UPLOADING TO GOOGLE DRIVE FOLDER ID {FINISHED_FOLDER_ID}")
    init_res = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
        headers={"Authorization": f"Bearer {DRIVE_TOKEN}", "Content-Type": "application/json"},
        json={"name": final_name, "parents": [FINISHED_FOLDER_ID]}
    )
    upload_url = init_res.headers["Location"]
    with open(final_name, "rb") as f:
        final_res = requests.put(upload_url, data=f.read())
    
    file_id = final_res.json().get('id')
    link = f"https://drive.google.com/file/d/{file_id}/view"
    log(f"🎉 SUCCESS! Final link: {link}")
    return link

# ==========================================
# 7. EXECUTION
# ==========================================
if __name__ == "__main__":
    log(f"🚀 Starting Deemcee Pipeline for {STUDENT_NAME}...")
    
    raw_id = search_drive_file(FILE_NAME, RAW_UPLOADS_FOLDER_ID)
    has_raw = download_file(raw_id, "raw_input.mp4")
    
    if not has_raw:
        log("❌ Cannot proceed without raw speech video.")
        sys.exit(1)
        
    eval_data = evaluate_video("raw_input.mp4")
    final_video_link = process_video()
        
    if WEB_APP_URL and eval_data and final_video_link:
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
