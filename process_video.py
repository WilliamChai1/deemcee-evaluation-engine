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

DEEMCEE_HASHTAGS = "#deemcee #deemceepinesquarekuching #speaklively #confidence #confidencebuilding #publicspeaking #malaysia #childreneducation #childhoodeducation #deemceepinesquare #pinesquare #batukawa #moyan #kuching #stage #shining #selfgrowth #enrichment"

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
# 2. OFFICIAL DEEMCEE 1-3 POINT EVALUATION ENGINE (AEM FORMAT)
# ==========================================
MASTER_CRITERIA = {
    "Body Actions": {
        "desc": "Students show energetic physical movements.",
        "3": "Shows very energetic movements",
        "2": "Shows somewhat energetic movements",
        "1": "Lacks energy in movements"
    },
    "Body Posture": {
        "desc": "Students maintain upright, confident posture without slouching.",
        "3": "Maintains perfect posture",
        "2": "Posture is mostly upright",
        "1": "Often slouches or has poor posture"
    },
    "Eye Contact": {
        "desc": "Students maintain consistent eye contact with audience, avoiding unnecessary movements.",
        "3": "Maintains strong eye contact",
        "2": "Maintains some eye contact",
        "1": "Avoids eye contact"
    },
    "Energy": {
        "desc": "Students demonstrate energy through voice volume and hand gestures.",
        "3": "Demonstrates high energy",
        "2": "Shows some energy",
        "1": "Lacks energy"
    },
    "Facial Expression": {
        "desc": "Students use appropriate facial expressions to convey emotions and reactions.",
        "3": "Demonstrates 2-3 expressive and appropriate facial expressions",
        "2": "Demonstrates 1-2 facial expressions with limited expressiveness",
        "1": "Demonstrates no or inappropriate facial expressions"
    },
    "Speaking Clarity": {
        "desc": "Students speak clearly and articulately, without mumbling.",
        "3": "Speaks very clearly",
        "2": "Speaks somewhat clearly",
        "1": "Often mumbles or is unclear"
    },
    "Intonation": {
        "desc": "Students vary their voice tone, using high and low pitches to convey ideas.",
        "3": "Varies voice tone effectively",
        "2": "Occasionally varies voice tone",
        "1": "Monotone, lacks variation"
    },
    "Fluency": {
        "desc": "Students speak smoothly without unnecessary pauses or fillers.",
        "3": "Speaks fluently with minimal pauses or hesitations",
        "2": "Speaks with some pauses or hesitations",
        "1": "Frequently pauses or hesitates while speaking"
    },
    "Voice Character": {
        "desc": "Students vary voice tone, pitch, and volume to match character in speech/role play.",
        "3": "Uses 2-3 different voice tones for different characters effectively",
        "2": "Uses 1-2 different voice tones with limited effectiveness",
        "1": "Uses the same voice tone for all characters"
    },
    "Action Demonstration": {
        "desc": "Students explain ideas clearly and demonstrate understanding through examples/actions.",
        "3": "Answers all action demonstration questions",
        "2": "Answers all action demonstration questions (> 75%)",
        "1": "Answers all action demonstration questions (50% - 75%)"
    },
    "Props": {
        "desc": "Students effectively use props to enhance their demonstration or role play.",
        "3": "Creative and effective use of props",
        "2": "Somewhat effective use of props",
        "1": "Minimal or ineffective use of props"
    },
    "Self Explanation": {
        "desc": "Students clearly articulate their thought process and reasoning behind actions/answers.",
        "3": "Provides detailed explanations with thorough reasoning (3-4 sentences)",
        "2": "Provides explanations with some detail and reasoning (2-3 sentences)",
        "1": "Provides brief and unclear explanations with limited reasoning (1-2 sentences)"
    },
    "Role Play": {
        "desc": "Students create and perform role plays based on given contexts, staying in character.",
        "3": "Creates role play scenarios creatively and independently without guidance",
        "2": "Creates role play scenarios with some creativity but requires occasional guidance",
        "1": "Cannot create role play scenarios and needs significant guidance"
    },
    "Application Sharing": {
        "desc": "Students share real-life applications or examples related to topic.",
        "3": "Answers all real-life application questions and assessment activities",
        "2": "Answers all real-life application questions (> 75%)",
        "1": "Answers all real-life application questions (50% - 75%)"
    },
    "Audience Engagement": {
        "desc": "Students actively connect with the audience through rhetorical questions and stage presence.",
        "3": "Actively engages and connects with audience throughout; highly compelling",
        "2": "Moderately engages audience with some effectiveness",
        "1": "Minimal or no audience engagement; delivers monologue"
    },
    "X-Factor & Stage Command": {
        "desc": "Demonstrates exceptional charisma, stage command, and distinctive personal style.",
        "3": "Captivating charisma and distinctive flair leaving a memorable impression",
        "2": "Confident stage presence with emerging personal style",
        "1": "Mechanical delivery; lacks stage presence or individuality"
    }
}

GRADE_ELEMENTS = {
    "1": ["Body Actions", "Body Posture", "Speaking Clarity"],
    "2": ["Body Actions", "Body Posture", "Speaking Clarity", "Eye Contact", "Intonation", "Energy", "Action Demonstration"],
    "3": ["Body Actions", "Body Posture", "Speaking Clarity", "Eye Contact", "Intonation", "Energy", "Action Demonstration", "Fluency", "Props", "Self Explanation", "Role Play", "Application Sharing"],
    "4": ["Body Actions", "Body Posture", "Eye Contact", "Energy", "Facial Expression", "Speaking Clarity", "Intonation", "Voice Character", "Fluency", "Action Demonstration", "Props", "Self Explanation", "Role Play", "Application Sharing"],
    "5": ["Body Actions", "Body Posture", "Eye Contact", "Energy", "Facial Expression", "Speaking Clarity", "Intonation", "Voice Character", "Fluency", "Action Demonstration", "Props", "Self Explanation", "Role Play", "Application Sharing", "Audience Engagement"],
    "6": ["Body Actions", "Body Posture", "Eye Contact", "Energy", "Facial Expression", "Speaking Clarity", "Intonation", "Voice Character", "Fluency", "Action Demonstration", "Props", "Self Explanation", "Role Play", "Application Sharing", "Audience Engagement", "X-Factor & Stage Command"]
}

def build_evaluation_prompt(grade: str, student: str, theme: str):
    grade_num = "".join(filter(str.isdigit, grade)) or "1"
    elements = GRADE_ELEMENTS.get(grade_num, GRADE_ELEMENTS["1"])
    max_score = len(elements) * 3
    pass_threshold = int(max_score * 0.70)

    rubric_text = ""
    for idx, el in enumerate(elements, start=1):
        info = MASTER_CRITERIA[el]
        rubric_text += f"{idx}. {el}\n   - Standard: {info['desc']}\n   - 3 Points: {info['3']}\n   - 2 Points: {info['2']}\n   - 1 Point: {info['1']}\n"

    prompt = f"""Role: Official Head Adjudicator for Deemcee Public Speaking Center.
Task: Rigorously evaluate speech performance for {student} (Grade {grade_num}, Theme: "{theme}").

OFFICIAL 1-3 POINT SCORING RUBRIC FOR GRADE {grade_num}:
{rubric_text}

SCORING RULES:
1. Score EVERY element strictly as 1, 2, or 3 points based on the explicit criteria above.
2. In the "feedback" field, you MUST provide precise timestamp evidence (e.g., "@ 0:18 - ...") explaining why the student earned a 1, 2, or 3.
3. Calculate "totalScore" by summing the scores of all {len(elements)} elements (Max: {max_score}).
4. "advanceRecommendation": Set strictly to "Yes" if totalScore >= {pass_threshold}, otherwise "Needs Practice".
5. Provide an empowering summary and a 2-step actionable Kaizen growth plan.

SOCIAL MEDIA CAPTION RULES (STRICT AEM FORMAT):
You must craft a detailed, encouraging, bilingual (English & Chinese) social media caption structured exactly in the Deemcee AEM Format:
- [A - Acknowledge]: Celebrate {student} taking the stage to embody their theme "{theme}" with courage and enthusiasm.
- [E - Encourage]: Identify the student's top-scoring elements (MAXIMUM 5 ELEMENTS). Detail exactly what they did well in each element with timestamp evidence from their performance.
- [M - Motivate]: Inspire {student} to keep shining and cultivating their public speaking superpower.
- End the caption with the official hashtags:
{DEEMCEE_HASHTAGS}

Respond strictly in valid JSON matching:
{{
  "studentName": "{student}",
  "gradeLevel": "Grade {grade_num}",
  "speechTheme": "{theme}",
  "encouragingSummary": "Empowering summary with timestamps",
  "elements": [
    {{
      "elementName": "Body Actions",
      "score": 3,
      "feedback": "Feedback with timestamp evidence @ 0:18"
    }}
  ],
  "totalScore": {pass_threshold + 2},
  "maxScore": {max_score},
  "advanceRecommendation": "Yes",
  "actionPlan": [
    "Tip 1: ...",
    "Tip 2: ..."
  ],
  "socialMediaCaption": "🌟 Grade {grade_num} Video Assignment 🌟 - I am a {theme} 🎙️✨\\n\\n[A - Acknowledge paragraph in EN & CN]\\n\\n[E - Detailed Encourage breakdown of max 5 top elements with timestamps in EN & CN]\\n\\n[M - Motivate closing in EN & CN]\\n\\n{DEEMCEE_HASHTAGS}"
}}"""
    return prompt

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

        system_instruction = build_evaluation_prompt(GRADE_LEVEL, STUDENT_NAME, THEME)

        gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{
                "role": "user",
                "parts": [
                    {"file_data": {"mime_type": "video/mp4", "file_uri": video_uri}},
                    {"text": "Evaluate speech against Deemcee standards and produce AEM social media caption."}
                ]
            }],
            "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"}
        }

        gen_res = requests.post(gen_url, json=payload).json()
        eval_json_text = gen_res["candidates"][0]["content"]["parts"][0]["text"]
        eval_data = json.loads(eval_json_text)
        log("✅ Deemcee AEM Evaluation & Caption complete!")

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
# 3. AUTO-DETECT GREEN SCREEN & SMART AUTO-FRAMING
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
            (int(w * 0.05), int(h * 0.50)),
            (int(w * 0.95), int(h * 0.50)),
        ]

        green_samples = []
        for x, y in sample_points:
            r, g, b = img.getpixel((x, y))
            if g > r and g > b:
                green_samples.append((r, g, b))

        if len(green_samples) > 0:
            count = len(green_samples)
            avg_r = int(sum(item[0] for item in green_samples) / count)
            avg_g = int(sum(item[1] for item in green_samples) / count)
            avg_b = int(sum(item[2] for item in green_samples) / count)
            detected_hex = f"0x{avg_r:02X}{avg_g:02X}{avg_b:02X}"
            log(f"🎯 Auto-Detected Green Screen Color: {detected_hex} (RGB: {avg_r}, {avg_g}, {avg_b})")
            return detected_hex
        else:
            return "0x00B800"
    except Exception as e:
        log(f"Auto-detect note: {e}")
        return "0x00B800"

def calculate_auto_centering_and_zoom(detected_hex: str) -> str:
    """Detects child's position and sizes them to ~68% of screen height in center."""
    if not os.path.exists(SAMPLE_FRAME):
        return ""
    try:
        img = Image.open(SAMPLE_FRAME).convert("RGB")
        w, h = img.size

        target_r = int(detected_hex[2:4], 16)
        target_g = int(detected_hex[4:6], 16)
        target_b = int(detected_hex[6:8], 16)

        non_green_x = []
        non_green_y = []

        for y in range(0, h, 6):
            for x in range(0, w, 6):
                r, g, b = img.getpixel((x, y))
                is_green = (g > r * 1.15 and g > b * 1.15) or (abs(g - target_g) < 30 and abs(r - target_r) < 30 and abs(b - target_b) < 30)
                if not is_green:
                    non_green_x.append(x)
                    non_green_y.append(y)

        if len(non_green_x) > 150:
            non_green_x.sort()
            non_green_y.sort()
            min_x = non_green_x[int(len(non_green_x) * 0.03)]
            max_x = non_green_x[int(len(non_green_x) * 0.97)]
            min_y = non_green_y[int(len(non_green_y) * 0.02)]
            max_y = non_green_y[int(len(non_green_y) * 0.98)]

            child_w = max_x - min_x
            child_h = max_y - min_y
            center_x = (min_x + max_x) // 2

            # Standardize child height to ~68% of frame height
            desired_crop_h = int(child_h / 0.68)
            desired_crop_h = min(h, max(desired_crop_h, int(h * 0.55)))
            desired_crop_w = int(desired_crop_h * (16 / 9))

            if desired_crop_w > w:
                desired_crop_w = w
                desired_crop_h = int(w * (9 / 16))

            crop_y = max(0, min_y - int(desired_crop_h * 0.12))
            if crop_y + desired_crop_h > h:
                crop_y = max(0, h - desired_crop_h)

            crop_x = max(0, min(w - desired_crop_w, center_x - (desired_crop_w // 2)))

            log(f"📐 Auto-Framing: Centering student at X={center_x}, Cropping {desired_crop_w}x{desired_crop_h} to scale size up naturally.")
            return f"crop={desired_crop_w}:{desired_crop_h}:{crop_x}:{crop_y},"
    except Exception as e:
        log(f"Auto-framing calculation note: {e}")
    return ""

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

            perm_url = f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions"
            requests.post(perm_url, headers={"Authorization": f"Bearer {DRIVE_TOKEN}"}, json={"role": "reader", "type": "anyone"}, timeout=15)

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
# 7. MAIN VIDEO COMPOSITOR (PRECISE CHROMAKEY + AUTO-FRAMING)
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

    # Step 2: Auto-detect exact green screen color & compute intelligent auto-framing
    detected_color = auto_detect_greenscreen_color(RAW_VIDEO)
    auto_framing_filter = calculate_auto_centering_and_zoom(detected_color)

    has_bg, has_logo = sanitize_images()
    temp_keyed = "temp_keyed.mp4"

    # Step 3: Precise Opacity Chromakey (0.06:0.08) - No Ghosting + Centered & Scaled Student
    log("🎬 Step 3: Processing Chroma Key & Branding...")
    if has_bg and has_logo:
        filter_complex = (
            "[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30[bg];"
            f"[0:v]{auto_framing_filter}scale=1920:1080:force_original_aspect_ratio=decrease,chromakey={detected_color}:0.06:0.08,despill=green,format=yuva420p,fps=30[fg];"
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
            f"[0:v]{auto_framing_filter}scale=1920:1080:force_original_aspect_ratio=decrease,chromakey={detected_color}:0.06:0.08,despill=green,format=yuva420p,fps=30[fg];"
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
    upload_directly_to_google_drive(FINAL_OUTPUT, FINISHED_FOLDER_ID)

if __name__ == "__main__":
    process_video()
