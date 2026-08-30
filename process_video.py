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
DRIVE_TOKEN = os.environ.get("DRIVE_TOKEN")
STUDENT_NAME = os.environ.get("STUDENT_NAME", "Student").strip()
GRADE_LEVEL = os.environ.get("GRADE_LEVEL", "Grade 1").strip()
THEME = os.environ.get("THEME", "pilot").lower().strip()
FILE_NAME = os.environ.get("FILE_NAME", "").strip()

# Deemcee Folder IDs
RAW_UPLOADS_FOLDER_ID = "1OU5MiRFWGWLoU3xxW5-VfVFnzamAmObY"
FINISHED_VIDEOS_FOLDER_ID = "1KjjL1O4LzSno5uELcgVQRQ_Otj4tW-io"
BRANDING_FOLDER_ID = "1U94j4vyMRnNgCes5Wuo4T0PhdkdW5iI4"
THEME_BACKGROUNDS_FOLDER_ID = "1KU3Qa9T0gdc3Z_bH6i3HRfSCyAD1KNqk"

headers = {"Authorization": f"Bearer {DRIVE_TOKEN}", "Accept": "application/json"}

def log(msg):
    print(msg, flush=True)

# ==========================================
# 2. GOOGLE DRIVE API HELPERS
# ==========================================
def search_drive_file(name, parent_id):
    query = f"'{parent_id}' in parents and name contains '{name}' and trashed=false"
    url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id, name)"
    res = requests.get(url, headers=headers).json()
    files = res.get("files", [])
    return files[0]["id"] if files else None

def download_file(file_id, dest_path):
    log(f"⬇️ Downloading to {dest_path}...")
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    res = requests.get(url, headers=headers, stream=True)
    with open(dest_path, "wb") as f:
        for chunk in res.iter_content(chunk_size=65536):
            if chunk: f.write(chunk)
    return os.path.exists(dest_path)

# ==========================================
# 3. GEMINI AI EVALUATION
# ==========================================
def evaluate_video(video_path):
    log("🧠 Starting Gemini AI Evaluation...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Upload to Gemini
    log("☁️ Uploading video to Gemini...")
    video_file = client.files.upload(file=video_path)
    
    # Wait for processing
    while video_file.state.name == "PROCESSING":
        log("⏳ Waiting for Gemini to process video...")
        time.sleep(10)
        video_file = client.files.get(name=video_file.name)
        
    if video_file.state.name == "FAILED":
        raise Exception("Gemini video processing failed.")

    # Dynamic Rubric based on Grade
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

    prompt = f"""Role: Expert public speaking evaluator for the Deemcee programme.
Task: Evaluate student speech video for {STUDENT_NAME} ({GRADE_LEVEL}, Theme: "{THEME}").
Rubric: [{current_rubric}].
Scoring: Strictly 1 to 10 for each element with timestamps.

Additionally, write a highly engaging social media caption that AEMs (Acknowledges, Encourages, Motivates) the student. 
Rules:
1. Opening: Start exactly with "🌟{GRADE_LEVEL} Video Assignment 🌟 - I am a {THEME} [add 2 relevant emojis]".
2. The AEM Body: Write a full 3-4 sentence paragraph highlighting their top scoring rubric elements. You MUST explicitly state *why* they did well based on the video.
3. Closing: End exactly with "Keep shining, {STUDENT_NAME}! We believe every child can grow with confidence and creativity. 🎊🎉"

Respond strictly in valid JSON format matching:
{{
  "encouragingSummary": "Summary",
  "elements": [ {{ "elementName": "Body Action", "score": 7, "feedback": "Feedback @ 0:15" }} ],
  "totalScore": 21,
  "maxScore": 30,
  "advanceRecommendation": "Yes",
  "actionPlan": ["Tip 1", "Tip 2"],
  "socialMediaCaption": "The full social media text."
}}"""

    log("🤖 Generating AI Evaluation...")
    response = client.models.generate_content(
        model='gemini-1.5-pro',
        contents=[video_file, "Watch this video and evaluate the student's performance."],
        config=types.GenerateContentConfig(
            system_instruction=prompt,
            response_mime_type="application/json",
            temperature=0.2
        )
    )
    
    # Save the raw JSON data for the Report Builder later
    with open("ai_evaluation.json", "w") as f:
        f.write(response.text)
    log("✅ AI Evaluation Saved.")

# ==========================================
# 4. FFMPEG VIDEO PROCESSING
# ==========================================
def get_green_screen_color(video_path):
    log("🔍 Auto-detecting green screen color...")
    subprocess.run(["ffmpeg", "-y", "-ss", "00:00:00.500", "-i", video_path, "-vframes", "1", "sample.png"], capture_output=True)
    try:
        img = Image.open("sample.png").convert("RGB")
        w, h = img.size
        # Sample corners
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
    # Setup Background & Logo
    bg_folder_id = search_drive_file(THEME, THEME_BACKGROUNDS_FOLDER_ID) or search_drive_file("default", THEME_BACKGROUNDS_FOLDER_ID)
    bg_file_id = search_drive_file(".png", bg_folder_id) if bg_folder_id else None
    logo_file_id = search_drive_file("logo", BRANDING_FOLDER_ID)
    
    if bg_file_id: download_file(bg_file_id, "bg.png")
    if logo_file_id: download_file(logo_file_id, "logo.png")

    color = get_green_screen_color(raw_video)
    final_name = f"{STUDENT_NAME}_{THEME}_Final.mp4".replace(" ", "_")
    
    log("🎬 Running FFmpeg Chroma Key Pipeline...")
    filter_complex = (
        "[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30[bg];"
        f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,chromakey={color}:0.05:0.10,despill=green,format=yuva420p,fps=30[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)[keyed];"
        "[2:v]scale=240:-1,format=yuva420p[logo];"
        "[keyed][logo]overlay=main_w-overlay_w-30:30[v_final]"
    )
    
    subprocess.run([
        "ffmpeg", "-y", "-i", raw_video, "-loop", "1", "-i", "bg.png", "-loop", "1", "-i", "logo.png",
        "-filter_complex", filter_complex, "-map", "[v_final]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
        "-shortest", final_name
    ], capture_output=True)
    
    log("☁️ Uploading Final Video to Drive...")
    init_res = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
        headers={"Authorization": f"Bearer {DRIVE_TOKEN}", "Content-Type": "application/json"},
        json={"name": final_name, "parents": [FINISHED_VIDEOS_FOLDER_ID]}
    )
    upload_url = init_res.headers["Location"]
    with open(final_name, "rb") as f:
        final_res = requests.put(upload_url, data=f.read())
    
    log(f"🎉 SUCCESS! Final video uploaded with ID: {final_res.json().get('id')}")

# ==========================================
# 5. EXECUTION PIPELINE
# ==========================================
if __name__ == "__main__":
    log(f"🚀 Starting Deemcee Pipeline for {STUDENT_NAME}...")
    raw_id = search_drive_file(FILE_NAME, RAW_UPLOADS_FOLDER_ID)
    if raw_id and download_file(raw_id, "raw_video.mp4"):
        evaluate_video("raw_video.mp4")
        process_and_upload("raw_video.mp4")
    else:
        log("❌ Failed to find or download the raw video.")
