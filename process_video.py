import os
import subprocess
import requests
import json
import time
import sys
from PIL import Image

def log(msg):
    print(msg, flush=True)

STUDENT_NAME = os.environ.get("STUDENT_NAME", "Student").strip()
THEME = os.environ.get("THEME", "pilot").lower().strip()
GRADE_LEVEL = os.environ.get("GRADE_LEVEL", "1").strip()
RAW_VIDEO_ID = os.environ.get("RAW_VIDEO_ID", "").strip()
BG_FILE_ID = os.environ.get("BG_FILE_ID", "").strip()
LOGO_FILE_ID = os.environ.get("LOGO_FILE_ID", "").strip()
INTRO_FILE_ID = os.environ.get("INTRO_FILE_ID", "").strip()
OUTRO_FILE_ID = os.environ.get("OUTRO_FILE_ID", "").strip()
DRIVE_TOKEN = os.environ.get("DRIVE_TOKEN", "").strip()
FINISHED_FOLDER_ID = os.environ.get("FINISHED_FOLDER_ID", "1yZ374vWosaiBwCp3RiWq1IjsVW7sDJAr").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
WEBAPP_URL = os.environ.get("WEBAPP_URL", "").strip()

log(f"🎬 Starting 16:9 Deemcee Video Processor for: {STUDENT_NAME} | Theme: {THEME} | Grade: {GRADE_LEVEL}")
log(f"📁 Destination Folder ID: {FINISHED_FOLDER_ID}")

RAW_VIDEO = "raw_input.mp4"
BG_IMAGE = "background_raw.png"
CLEAN_BG = "clean_bg.png"
LOGO_IMAGE = "logo_raw.png"
CLEAN_LOGO = "clean_logo.png"
INTRO_VIDEO = "intro.mp4"
OUTRO_VIDEO = "outro.mp4"
SAMPLE_FRAME = "sample_frame.png"
FINAL_OUTPUT = f"{STUDENT_NAME}_{THEME}_Evaluation_Final.mp4"

# ==========================================
# 1. DOWNLOAD ASSETS VIA OFFICIAL DRIVE API
# ==========================================
def download_drive_file(file_id: str, dest_path: str):
    if not file_id:
        log(f"ℹ️ No Drive File ID provided for {dest_path}")
        return False
    try:
        log(f"⬇️ Downloading {dest_path} via Drive API (ID: {file_id})...")
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        headers = {"Authorization": f"Bearer {DRIVE_TOKEN}"} if DRIVE_TOKEN else {}

        res = requests.get(url, headers=headers, stream=True)
        if res.status_code == 200:
            with open(dest_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            log(f"✅ Downloaded {dest_path} ({os.path.getsize(dest_path)} bytes)")
            return True
        else:
            log(f"❌ Drive API download failed for {dest_path}: HTTP {res.status_code}")
            return False
    except Exception as e:
        log(f"❌ Error downloading {dest_path}: {e}")
        return False

# ==========================================
# 2. GEMINI SPEECH EVALUATION & SOCIAL CAPTION
# ==========================================
def evaluate_speech_with_gemini(video_path: str):
    if not GEMINI_API_KEY or not os.path.exists(video_path):
        return None
    try:
        log("🤖 Step 1: Uploading video to Gemini File API for evaluation...")
        file_size = os.path.getsize(video_path)
        
        init_url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={GEMINI_API_KEY}"
        init_headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": "video/mp4",
            "Content-Type": "application/json"
        }
        init_res = requests.post(init_url, headers=init_headers, json={"file": {"display_name": f"{STUDENT_NAME}_speech"}})
        upload_url = init_res.headers.get("x-goog-upload-url") or init_res.headers.get("X-Goog-Upload-URL")
        
        if not upload_url:
            log(f"❌ Gemini Upload Init Failed: {init_res.text}")
            return None

        with open(video_path, "rb") as f:
            upload_res = requests.post(
                upload_url,
                headers={"X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"},
                data=f
            )
        
        file_data = upload_res.json()
        video_uri = file_data["file"]["uri"]
        video_name = file_data["file"]["name"]

        check_url = f"https://generativelanguage.googleapis.com/v1beta/{video_name}?key={GEMINI_API_KEY}"
        for _ in range(25):
            time.sleep(4)
            chk = requests.get(check_url).json()
            if chk.get("state") == "ACTIVE":
                break
        
        rubrics = {
            "1": "body action, body posture, speaking clarity",
            "2": "body action, body posture, speaking clarity, eye contact, intonation, energy, action demonstration",
            "3": "body action, body posture, speaking clarity, eye contact, intonation, energy, action demonstration, fluency, props, self-explaination, role play and application sharing",
            "4": "body action, body posture, speaking clarity, eye contact, intonation, energy, action demonstration, fluency, props, self-explaination, role play, application sharing, voice character and facial expression",
            "5": "body action, body posture, speaking clarity, eye contact, intonation, energy, action demonstration, fluency, props, self-explaination, role play, application sharing, voice character, facial expression and audience engagement",
            "6": "body action, body posture, speaking clarity, eye contact, intonation, energy, action demonstration, fluency, props, self-explaination, role play, application sharing, voice character, facial expression, audience engagement and x-factor"
        }
        selected_rubric = rubrics.get(GRADE_LEVEL, rubrics["1"])

        system_instruction = f"""Role: Expert public speaking evaluator for the Deemcee programme.
Task: Evaluate student speech video for {STUDENT_NAME} (Grade {GRADE_LEVEL}, Theme: "{THEME}").
Rubric: [{selected_rubric}].
Scoring: Strictly 1 to 10 for each element with timestamps.

Respond strictly in valid JSON matching:
{{
  "studentName": "{STUDENT_NAME}",
  "gradeLevel": "Grade {GRADE_LEVEL}",
  "speechTheme": "{THEME}",
  "encouragingSummary": "Summary with timestamp evidence",
  "elements": [
    {{ "elementName": "Body Action", "score": 9, "feedback": "Feedback with timestamps" }}
  ],
  "totalScore": 25,
  "maxScore": 30,
  "advanceRecommendation": "Yes",
  "actionPlan": ["Actionable tip 1", "Actionable tip 2"],
  "socialMediaCaption": "Encouraging bilingual English & Chinese caption ready for Instagram Reels & Facebook with hashtags #Deemcee #PublicSpeakingForKids"
}}"""

        gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{
                "role": "user",
                "parts": [
                    {"file_data": {"mime_type": "video/mp4", "file_uri": video_uri}},
                    {"text": "Evaluate the speech video and output only the required JSON."}
                ]
            }],
            "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"}
        }

        gen_res = requests.post(gen_url, json=payload).json()
        eval_json_text = gen_res["candidates"][0]["content"]["parts"][0]["text"]
        eval_data = json.loads(eval_json_text)
        log("✅ Gemini Evaluation & Caption complete!")

        # Send evaluation and caption back to Apps Script to generate Google Docs in Drive
        if WEBAPP_URL:
            try:
                res = requests.post(WEBAPP_URL, json={
                    "action": "save_reports",
                    "student_name": STUDENT_NAME,
                    "grade_level": GRADE_LEVEL,
                    "theme": THEME,
                    "eval_data": eval_data
                }, timeout=30, allow_redirects=True)
                log(f"📁 Reports filed successfully in Drive: {res.text}")
            except Exception as ex:
                log(f"Warning calling Webapp for docs: {ex}")

        return eval_data

    except Exception as e:
        log(f"Evaluation error: {e}")
        return None

# ==========================================
# 3. AUTO-DETECT EXACT GREEN SCREEN COLOR
# ==========================================
def auto_detect_greenscreen_color(video_path: str) -> str:
    log("🔍 Step 2: Analyzing video to auto-detect exact green screen color...")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-ss", "00:00:00.500", "-i", video_path,
            "-vframes", "1", SAMPLE_FRAME
        ], capture_output=True, text=True)

        if not os.path.exists(SAMPLE_FRAME):
            return "0x00B800"

        img = Image.open(SAMPLE_FRAME).convert("RGB")
        w, h = img.size

        sample_points = [
            (int(w * 0.05), int(h * 0.05)),
            (int(w * 0.95), int(h * 0.05)),
            (int(w * 0.50), int(h * 0.05)),
            (int(w * 0.25), int(h * 0.05)),
            (int(w * 0.75), int(h * 0.05)),
            (int(w * 0.05), int(h * 0.20)),
            (int(w * 0.95), int(h * 0.20)),
            (int(w * 0.05), int(h * 0.35)),
            (int(w * 0.95), int(h * 0.35)),
        ]

        green_samples = []
        for x, y in sample_points:
            r, g, b = img.getpixel((x, y))
            if g > r and g > b:
                green_samples.append((r, g, b))

        if len(green_samples) > 0:
            count = len(green_samples)
            avg_r = int(sum(item[0] for item in green_samples) / count)
            avg_g = int(sum(item for item in green_samples) / count)
            avg_b = int(sum(item for item in green_samples) / count)

            detected_hex = f"0x{avg_r:02X}{avg_g:02X}{avg_b:02X}"
            log(f"🎯 Auto-Detected Green Screen Color: {detected_hex} (RGB: {avg_r}, {avg_g}, {avg_b})")
            return detected_hex
        else:
            return "0x00B800"
    except Exception as e:
        log(f"Auto-detect note: {e}")
        return "0x00B800"

# ==========================================
# 4. UPLOAD FINAL 16:9 VIDEO TO GOOGLE DRIVE
# ==========================================
def upload_directly_to_google_drive(video_path: str, folder_id: str):
    if not DRIVE_TOKEN or not folder_id:
        log("⚠️ Missing DRIVE_TOKEN or FINISHED_FOLDER_ID.")
        return None

    log(f"☁️ Uploading {video_path} directly to Final Deliverables folder ({folder_id})...")
    
    try:
        init_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"
        init_headers = {
            "Authorization": f"Bearer {DRIVE_TOKEN}",
            "Content-Type": "application/json; charset=UTF-8"
        }
        metadata = {
            "name": FINAL_OUTPUT,
            "parents": [folder_id]
        }
        
        init_res = requests.post(init_url, headers=init_headers, json=metadata, timeout=30)
        if init_res.status_code != 200:
            log(f"❌ Drive API Init Error (HTTP {init_res.status_code}): {init_res.text}")
            return None

        upload_url = init_res.headers.get("Location")
        if not upload_url:
            return None

        with open(video_path, "rb") as f:
            video_data = f.read()

        upload_headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(len(video_data))
        }
        
        upload_res = requests.put(upload_url, headers=upload_headers, data=video_data, timeout=300)
        
        if upload_res.status_code in [200, 201]:
            file_data = upload_res.json()
            file_id = file_data.get("id")
            web_link = f"https://drive.google.com/file/d/{file_id}/view"
            log("=====================================================")
            log(f"🎉 SUCCESS! 16:9 Video uploaded to Final Deliverables!")
            log(f"📁 File Name: {FINAL_OUTPUT}")
            log(f"🔗 Google Drive Video Link: {web_link}")
            log("=====================================================")

            # Set public view permission
            perm_url = f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions"
            requests.post(perm_url, headers={"Authorization": f"Bearer {DRIVE_TOKEN}"}, json={"role": "reader", "type": "anyone"}, timeout=15)

            # Update Deemcee Status Board with final video link
            if WEBAPP_URL:
                try:
                    requests.post(WEBAPP_URL, json={"action": "video_completed", "video_url": web_link}, timeout=15, allow_redirects=True)
                except Exception as ex:
                    log(f"Warning updating Status Board: {ex}")

            return web_link
        else:
            log(f"❌ Drive Upload Error (HTTP {upload_res.status_code}): {upload_res.text}")
            return None
    except Exception as e:
        log(f"❌ Upload Exception: {e}")
        return None

# ==========================================
# 5. SANITIZE IMAGES (PNG RGB24/RGBA)
# ==========================================
def sanitize_images():
    has_clean_bg = False
    has_clean_logo = False

    if os.path.exists(BG_IMAGE) and os.path.getsize(BG_IMAGE) > 1024:
        try:
            res = subprocess.run([
                "ffmpeg", "-y", "-i", BG_IMAGE,
                "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=rgb24",
                "-vframes", "1", CLEAN_BG
            ], capture_output=True, text=True)
            if res.returncode == 0:
                has_clean_bg = True
                log("✅ Background sanitized to 16:9 PNG.")
            else:
                log(f"❌ Background sanitize error: {res.stderr[:200]}")
        except Exception as e:
            log(f"❌ Background sanitize exception: {e}")

    if os.path.exists(LOGO_IMAGE) and os.path.getsize(LOGO_IMAGE) > 1024:
        try:
            res = subprocess.run([
                "ffmpeg", "-y", "-i", LOGO_IMAGE,
                "-vf", "scale=240:-1,format=rgba",
                "-vframes", "1", CLEAN_LOGO
            ], capture_output=True, text=True)
            if res.returncode == 0:
                has_clean_logo = True
                log("✅ Deemcee Logo sanitized to clean PNG.")
            else:
                log(f"❌ Logo sanitize error: {res.stderr[:200]}")
        except Exception as e:
            log(f"❌ Logo sanitize exception: {e}")

    return has_clean_bg, has_clean_logo

def run_ffmpeg_command(cmd, step_name="FFmpeg"):
    log(f"🚀 Running {step_name}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        log(f"❌ {step_name} Failed:\n{res.stderr}")
        raise RuntimeError(f"{step_name} failed with exit code {res.returncode}")
    return res

# ==========================================
# 6. NORMALIZE INTRO / OUTRO CLIPS
# ==========================================
def normalize_clip(input_path, output_path, step_name):
    log(f"🎬 Normalizing {step_name} ({input_path})...")
    has_audio = False
    try:
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=codec_type", "-of", "csv=p=0", input_path
        ], capture_output=True, text=True)
        has_audio = "audio" in probe.stdout.lower()
    except Exception:
        has_audio = False

    if has_audio:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,format=yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
            output_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,format=yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path
        ]
    run_ffmpeg_command(cmd, step_name)

# ==========================================
# 7. MAIN VIDEO COMPOSITOR
# ==========================================
def process_video():
    has_raw = download_drive_file(RAW_VIDEO_ID, RAW_VIDEO)
    download_drive_file(BG_FILE_ID, BG_IMAGE)
    download_drive_file(LOGO_FILE_ID, LOGO_IMAGE)
    has_intro = download_drive_file(INTRO_FILE_ID, INTRO_VIDEO)
    has_outro = download_drive_file(OUTRO_FILE_ID, OUTRO_VIDEO)

    if not has_raw:
        log("❌ Cannot proceed without raw speech video.")
        return

    # Step 1: Run Gemini Speech Evaluation & Build Docs in Drive
    evaluate_speech_with_gemini(RAW_VIDEO)

    # Step 2: Auto-detect exact green screen color from this specific recording
    detected_color = auto_detect_greenscreen_color(RAW_VIDEO)

    has_bg, has_logo = sanitize_images()
    temp_keyed = "temp_keyed.mp4"

    # Step 3: Chroma Key + 16:9 Theme Background + Top-Right Logo
    log("🎬 Step 3: Processing Chroma Key & Branding...")
    if has_bg and has_logo:
        filter_complex = (
            "[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30[bg];"
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,colorkey={detected_color}:0.30:0.03,despill=green,format=yuva420p,fps=30[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)[keyed];"
            "[2:v]scale=240:-1,format=yuva420p[logo];"
            "[keyed][logo]overlay=main_w-overlay_w-30:30[v_final]"
        )
        cmd1 = [
            "ffmpeg", "-y",
            "-i", RAW_VIDEO,
            "-loop", "1", "-i", CLEAN_BG,
            "-loop", "1", "-i", CLEAN_LOGO,
            "-filter_complex", filter_complex,
            "-map", "[v_final]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-c:a", "aac",
            "-ar", "44100",
            "-ac", "2",
            "-b:a", "192k",
            "-shortest",
            temp_keyed
        ]
    elif has_bg:
        filter_complex = (
            "[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30[bg];"
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,colorkey={detected_color}:0.30:0.03,despill=green,format=yuva420p,fps=30[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)[v_final]"
        )
        cmd1 = [
            "ffmpeg", "-y",
            "-i", RAW_VIDEO,
            "-loop", "1", "-i", CLEAN_BG,
            "-filter_complex", filter_complex,
            "-map", "[v_final]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-c:a", "aac",
            "-ar", "44100",
            "-ac", "2",
            "-b:a", "192k",
            "-shortest",
            temp_keyed
        ]
    else:
        cmd1 = [
            "ffmpeg", "-y",
            "-i", RAW_VIDEO,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-c:a", "aac",
            "-ar", "44100",
            "-ac", "2",
            temp_keyed
        ]

    run_ffmpeg_command(cmd1, "Chroma Key & Branding")
    log("✅ Chroma Key step complete!")

    # Step 4: Normalize Intro & Outro and Stitch
    if has_intro and has_outro:
        normalize_clip(INTRO_VIDEO, "norm_intro.mp4", "Intro Video")
        normalize_clip(OUTRO_VIDEO, "norm_outro.mp4", "Outro Video")

        with open("concat_list.txt", "w") as f:
            f.write("file 'norm_intro.mp4'\n")
            f.write(f"file '{temp_keyed}'\n")
            f.write("file 'norm_outro.mp4'\n")

        run_ffmpeg_command([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat_list.txt",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            FINAL_OUTPUT
        ], "Concatenation")
    else:
        os.rename(temp_keyed, FINAL_OUTPUT)

    log(f"🎉 16:9 Final Video Ready: {FINAL_OUTPUT} ({os.path.getsize(FINAL_OUTPUT)} bytes)")

    # Step 5: Direct API Upload to Final Deliverables in Google Drive
    upload_directly_to_google_drive(FINAL_OUTPUT, FINISHED_FOLDER_ID)

if __name__ == "__main__":
    process_video()
