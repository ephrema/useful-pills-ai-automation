import os, sys, json, re, time, math, random, subprocess, textwrap
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
OUT = ROOT / "output"
CACHE = ROOT / ".cache" / "piper"
STATE_FILE = ROOT / "state" / "history.json"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
TIMEZONE = os.getenv("TIMEZONE", "Africa/Addis_Ababa")
LONG_HOUR = int(os.getenv("LONG_PUBLISH_HOUR", "18"))
SHORT_HOUR = int(os.getenv("SHORT_PUBLISH_HOUR", "20"))
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
CHANNEL = "Useful Pills AI"

PLAYLISTS = {
    "Science and Amazing Facts": "Amazing Science Facts",
    "Psychology and Human Behavior": "Psychology Explained",
    "Technology and Artificial Intelligence": "Technology and Artificial Intelligence",
    "History and Mysteries": "History and Mysteries",
    "Brain Games and Riddles": "Brain Games and Riddles",
    "Life Hacks and Useful Knowledge": "Life Hacks and Useful Tips",
    "Money and Business Knowledge": "Money and Business Knowledge",
    "Nature and Amazing Discoveries": "Nature and Amazing Discoveries",
    "Shorts": "Useful Pills AI Shorts",
}
CATEGORIES = list(PLAYLISTS.keys())[:-1]

def log(msg):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)

def load_state():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"published_dates": {}, "recent_topics": [], "playlist_ids": {}}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

def validate():
    missing = [k for k in ["GEMINI_API_KEY", "YOUTUBE_CLIENT_ID",
               "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"] if not os.getenv(k)]
    if missing:
        raise RuntimeError("Missing GitHub Actions secrets: " + ", ".join(missing))
    if not (0 <= LONG_HOUR <= 23 and 0 <= SHORT_HOUR <= 23):
        raise RuntimeError("Publish hours must be 0..23.")
    if LONG_HOUR == SHORT_HOUR:
        raise RuntimeError("Long and Short publish hours must differ.")
    subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.DEVNULL)
    log("Configuration validation passed.")

def gemini(prompt, use_search=True):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.65, "maxOutputTokens": 10000}
    }
    if use_search:
        payload["tools"] = [{"google_search": {}}]
    response = requests.post(
        url, params={"key": GEMINI_KEY}, json=payload, timeout=180
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini API {response.status_code}: {response.text[:1500]}")
    data = response.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "\n".join(p.get("text", "") for p in parts if "text" in p)
    if not text.strip():
        raise RuntimeError("Gemini returned an empty response.")
    return text, data

def extract_json(text):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Model did not return a JSON object.")
    return json.loads(cleaned[start:end+1])

def build_content(state, today):
    recent = state.get("recent_topics", [])[-45:]
    category = CATEGORIES[(today.toordinal() // 1) % len(CATEGORIES)]
    research_prompt = f"""
You are the research editor for {CHANNEL}, an educational entertainment channel.
Today's category: {category}.
Avoid these recently covered topics: {json.dumps(recent, ensure_ascii=False)}.
Use Google Search grounding. Find a fresh, interesting, evergreen topic with reliable
sources. Do not use breaking news that may become outdated. Avoid medical diagnosis,
personal financial/legal advice, political persuasion, conspiracy claims, dangerous
experiments, and fabricated facts.
Return only JSON:
{{"topic":"...","angle":"...","category":"...","why_interesting":"...",
"key_facts":[{{"claim":"...","source_url":"https://..."}},...],
"source_urls":["https://..."]}}
Provide at least 4 factual claims with source URLs. If evidence is weak, choose another topic.
"""
    research_text, research_raw = gemini(research_prompt, True)
    research = extract_json(research_text)

    creation_prompt = f"""
Create an original YouTube content package for {CHANNEL}.
Research dossier:
{json.dumps(research, ensure_ascii=False)}

Return ONLY valid JSON with exactly these keys:
{{
 "topic":"...",
 "category":"one of {CATEGORIES}",
 "long_title":"...",
 "long_description":"...",
 "tags":["..."],
 "long_script":"850 to 1050 spoken words. Original, clear, engaging English. Strong 10-second hook.
 Explain the topic accurately, use examples and transitions, avoid filler, end with a natural CTA.",
 "short_title":"... #Shorts",
 "short_description":"...",
 "short_script":"90 to 125 spoken words, self-contained hook and payoff, not merely a chopped sentence.",
 "scenes":[{{"heading":"...","visual_query":"2-5 words for a relevant real stock video search",
 "on_screen_text":"short phrase","narration_section":"one or two sentences"}}],
 "short_scenes":[{{"heading":"...","visual_query":"...","on_screen_text":"..."}}],
 "thumbnail_text":"2 to 5 words",
 "sources":["full source URLs"],
 "needs_realistic_ai_disclosure":false,
 "quality_notes":"..."
}}
Rules:
- Create 10 to 14 long scenes and 4 to 6 Short scenes.
- Every scene must match the narration and not repeat the same visual idea.
- No copied wording from other creators.
- Do not invent quotes, statistics, experiments, or historical events.
- Use cautious language where evidence is uncertain.
- No medical, financial, or legal advice.
- The title must be accurate, not misleading or sensational.
- Include sources in the description.
- Avoid generic intros such as "Welcome back".
"""
    content_text, content_raw = gemini(creation_prompt, True)
    content = extract_json(content_text)

    review_prompt = f"""
Act as a strict fact-checking and YouTube quality editor.
Review this package against its research dossier.
Research: {json.dumps(research, ensure_ascii=False)}
Package: {json.dumps(content, ensure_ascii=False)}
Return ONLY JSON:
{{"pass":true_or_false,"score":0_to_100,"issues":["..."],
"corrections":["..."],"final_long_script":"complete corrected script",
"final_short_script":"complete corrected Short script",
"final_long_title":"...",
"final_short_title":"..."}}
Reject if there are unsupported facts, invented numbers, plagiarism-like wording,
dangerous instructions, misleading claims, repetitive filler, or missing educational value.
Require score >= 85. If evidence is weak, fail.
"""
    review_text, review_raw = gemini(review_prompt, True)
    review = extract_json(review_text)
    if not review.get("pass") or int(review.get("score", 0)) < 85:
        raise RuntimeError("Automated quality gate rejected content: " +
                           json.dumps(review.get("issues", []), ensure_ascii=False))
    content["long_script"] = review.get("final_long_script") or content["long_script"]
    content["short_script"] = review.get("final_short_script") or content["short_script"]
    content["long_title"] = review.get("final_long_title") or content["long_title"]
    content["short_title"] = review.get("final_short_title") or content["short_title"]
    content["research_dossier"] = research
    content["review"] = review
    return content

def ensure_piper():
    CACHE.mkdir(parents=True, exist_ok=True)
    model = CACHE / "en_US-lessac-medium.onnx"
    config = CACHE / "en_US-lessac-medium.onnx.json"
    base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/"
    for path, name in [(model, "en_US-lessac-medium.onnx"),
                       (config, "en_US-lessac-medium.onnx.json")]:
        if not path.exists():
            log(f"Downloading Piper voice file {name}")
            r = requests.get(base + name, timeout=180)
            r.raise_for_status()
            path.write_bytes(r.content)
    return model

def make_voice(text, output):
    model = ensure_piper()
    proc = subprocess.run(
        ["piper", "--model", str(model), "--output_file", str(output)],
        input=text, text=True, capture_output=True, timeout=900
    )
    if proc.returncode != 0:
        raise RuntimeError("Piper failed: " + proc.stderr[-2000:])
    if not output.exists() or output.stat().st_size < 10000:
        raise RuntimeError("Piper produced no usable audio.")
    return output

def pexels_clip(query, destination, orientation="landscape"):
    if not PEXELS_KEY:
        return None, None
    try:
        r = requests.get(
            "https://api.pexels.com/v1/videos/search",
            headers={"Authorization": PEXELS_KEY},
            params={"query": query, "per_page": 8, "orientation": orientation},
            timeout=60
        )
        r.raise_for_status()
        videos = r.json().get("videos", [])
        if not videos:
            return None, None
        candidates = []
        for video in videos:
            for vf in video.get("video_files", []):
                link = vf.get("link")
                width, height = vf.get("width") or 0, vf.get("height") or 0
                if link and width >= 640 and height >= 360:
                    candidates.append((width * height, link, video))
        if not candidates:
            return None, None
        _, link, video = sorted(candidates, key=lambda x: x[0], reverse=True)[0]
        media = requests.get(link, timeout=180)
        media.raise_for_status()
        destination.write_bytes(media.content)
        user = video.get("user", {})
        attribution = {
            "name": user.get("name", "Pexels contributor"),
            "url": user.get("url", "https://www.pexels.com"),
            "page": video.get("url", "https://www.pexels.com")
        }
        return destination, attribution
    except Exception as exc:
        log(f"Pexels lookup failed for '{query}': {exc}")
        return None, None

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        if draw.textbbox((0,0), test, font=font)[2] <= max_width:
            line = test
        else:
            if line: lines.append(line)
            line = word
    if line: lines.append(line)
    return lines

def make_overlay(text, width, height, outpath):
    overlay = Image.new("RGBA", (width, height), (0,0,0,0))
    d = ImageDraw.Draw(overlay)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font = ImageFont.truetype(font_path, 42 if width > 1000 else 34)
    d.rectangle((0, height-190, width, height), fill=(0,0,0,155))
    lines = wrap_text(d, text, font, width-100)
    y = height-160
    for line in lines[:2]:
        bbox = d.textbbox((0,0), line, font=font)
        x = (width - (bbox[2]-bbox[0]))//2
        d.text((x,y), line, font=font, fill=(255,255,255,255), stroke_width=1, stroke_fill=(0,0,0,255))
        y += 55
    overlay.save(outpath)

def make_fallback_clip(text, destination, width, height, seconds):
    img = Image.new("RGB", (width, height), (18, 30, 52))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                              66 if width > 1000 else 48)
    lines = wrap_text(d, text, font, width-140)
    total_h = len(lines[:4]) * 85
    y = (height-total_h)//2
    for line in lines[:4]:
        b = d.textbbox((0,0), line, font=font)
        x = (width-(b[2]-b[0]))//2
        d.text((x,y), line, font=font, fill="white")
        y += 85
    still = destination.with_suffix(".png")
    img.save(still)
    subprocess.run([
        "ffmpeg","-y","-loop","1","-i",str(still),"-t",str(seconds),
        "-vf",f"scale={width}:{height},fps=25,format=yuv420p",
        "-an","-c:v","libx264","-preset","veryfast","-crf","27",str(destination)
    ],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def render_video(scenes, audio, output, orientation="landscape", attribution_list=None):
    width, height = (1920,1080) if orientation == "landscape" else (1080,1920)
    duration = probe_duration(audio)
    count = max(1, len(scenes))
    seg_duration = duration / count
    temp = output.parent / (output.stem + "_segments")
    temp.mkdir(parents=True, exist_ok=True)
    segment_paths = []
    for i, scene in enumerate(scenes):
        query = scene.get("visual_query") or scene.get("heading") or "science nature technology"
        clip_path = temp / f"source_{i:02d}.mp4"
        segment_path = temp / f"segment_{i:02d}.mp4"
        downloaded, attribution = pexels_clip(query, clip_path, orientation)
        if attribution and attribution_list is not None:
            attribution_list.append(attribution)
        if downloaded:
            vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=25,format=yuv420p"
            subprocess.run([
                "ffmpeg","-y","-stream_loop","-1","-i",str(downloaded),
                "-t",str(seg_duration),"-vf",vf,"-an","-c:v","libx264",
                "-preset","veryfast","-crf","25",str(segment_path)
            ],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:
            make_fallback_clip(scene.get("on_screen_text") or scene.get("heading") or query,
                               segment_path,width,height,seg_duration)
        overlay = temp / f"overlay_{i:02d}.png"
        make_overlay(scene.get("on_screen_text") or scene.get("heading") or "", width, height, overlay)
        over_segment = temp / f"over_{i:02d}.mp4"
        subprocess.run([
            "ffmpeg","-y","-i",str(segment_path),"-i",str(overlay),
            "-filter_complex","[0:v][1:v]overlay=0:0:format=auto",
            "-t",str(seg_duration),"-an","-c:v","libx264","-preset","veryfast",
            "-crf","25","-pix_fmt","yuv420p",str(over_segment)
        ],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        segment_paths.append(over_segment)

    concat_file = temp / "concat.txt"
    concat_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in segment_paths), encoding="utf-8")
    silent = temp / "silent.mp4"
    subprocess.run([
        "ffmpeg","-y","-f","concat","-safe","0","-i",str(concat_file),
        "-c","copy",str(silent)
    ],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    subprocess.run([
        "ffmpeg","-y","-i",str(silent),"-i",str(audio),
        "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac",
        "-b:a","160k","-shortest","-movflags","+faststart",str(output)
    ],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return output

def probe_duration(path):
    out = subprocess.check_output([
        "ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=noprint_wrappers=1:nokey=1",str(path)
    ],text=True)
    return float(out.strip())

def make_thumbnail(text, output):
    w,h = 1280,720
    img = Image.new("RGB",(w,h),(12,24,48))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",88)
    lines = wrap_text(d, text.upper(), font, w-120)
    y = (h-min(3,len(lines))*110)//2
    for line in lines[:3]:
        b=d.textbbox((0,0),line,font=font)
        x=(w-(b[2]-b[0]))//2
        d.text((x,y),line,font=font,fill=(255,255,255))
        y += 110
    img.save(output,quality=92)

def youtube_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube"]
    )
    creds.refresh(Request())
    return build("youtube","v3",credentials=creds,cache_discovery=False)

def ensure_playlists(youtube, state):
    ids = state.setdefault("playlist_ids", {})
    existing = {}
    token = None
    while True:
        response = youtube.playlists().list(
            part="snippet", mine=True, maxResults=50, pageToken=token
        ).execute()
        for item in response.get("items",[]):
            existing[item["snippet"]["title"]] = item["id"]
        token = response.get("nextPageToken")
        if not token: break
    for title in PLAYLISTS.values():
        if title in existing:
            ids[title] = existing[title]
        elif title not in ids:
            result = youtube.playlists().insert(
                part="snippet,status",
                body={"snippet":{"title":title,"description":f"{title} — {CHANNEL}"},
                      "status":{"privacyStatus":"public"}}
            ).execute()
            ids[title] = result["id"]
    save_state(state)
    return ids

def next_publish_time(hour, minute=0):
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    target = now.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if target <= now + timedelta(minutes=10):
        target += timedelta(days=1)
    return target.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def upload_video(youtube, path, title, description, tags, publish_at, playlist_id):
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:25],
            "categoryId": "27",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en"
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at,
            "selfDeclaredMadeForKids": False
        }
    }
    media = MediaFileUpload(str(path),mimetype="video/mp4",chunksize=8*1024*1024,resumable=True)
    request = youtube.videos().insert(part="snippet,status",body=body,media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log(f"Upload progress: {int(status.progress()*100)}%")
    video_id = response["id"]
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(path.with_suffix(".jpg")),mimetype="image/jpeg")
        ).execute()
    except Exception as exc:
        log(f"Thumbnail upload warning for {video_id}: {exc}")
    if playlist_id:
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={"snippet":{"playlistId":playlist_id,
                                 "resourceId":{"kind":"youtube#video","videoId":video_id}}}
            ).execute()
        except Exception as exc:
            log(f"Playlist assignment warning for {video_id}: {exc}")
    log(f"Uploaded {video_id}: {title}")
    return video_id

def add_pexels_attribution(description, attributions):
    unique = {}
    for a in attributions:
        unique[a.get("page")] = a
    if not unique:
        return description + "\n\nVisuals: original generated text-card graphics."
    lines = ["\n\nStock footage credits (Pexels):"]
    for a in list(unique.values())[:20]:
        lines.append(f"- {a['name']}: {a['page']}")
    lines.append("Pexels: https://www.pexels.com/")
    return description + "\n" + "\n".join(lines)

def create_daily():
    WORK.mkdir(exist_ok=True,parents=True)
    OUT.mkdir(exist_ok=True,parents=True)
    state = load_state()
    local_now = datetime.now(ZoneInfo(TIMEZONE))
    date_key = local_now.strftime("%Y-%m-%d")
    date_record = state.get("published_dates", {}).get(date_key, {})
    if date_record.get("long_video_id") and date_record.get("short_video_id"):
        log(f"Both videos already uploaded for {date_key}; skipping.")
        return

    # Persist the generated package so a retry does not create a different Short
    # after the long video has already been uploaded.
    content_path = ROOT / "state" / f"content_{date_key}.json"
    if content_path.exists():
        content = json.loads(content_path.read_text(encoding="utf-8"))
        log(f"Reusing saved content package for {date_key}.")
    else:
        content = build_content(state, local_now)
        content_path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    topic = content["topic"]
    log(f"Selected topic: {topic}")

    # Long video production
    long_audio = WORK / "long.wav"
    make_voice(content["long_script"],long_audio)
    long_attrs = []
    long_mp4 = OUT / f"{date_key}_long.mp4"
    render_video(content["scenes"],long_audio,long_mp4,"landscape",long_attrs)
    long_thumb = long_mp4.with_suffix(".jpg")
    make_thumbnail(content.get("thumbnail_text") or content["long_title"],long_thumb)
    long_desc = content.get("long_description","") + "\n\nSources:\n" + "\n".join(content.get("sources",[]))
    long_desc = add_pexels_attribution(long_desc,long_attrs)

    # Short production
    short_audio = WORK / "short.wav"
    make_voice(content["short_script"],short_audio)
    short_attrs = []
    short_mp4 = OUT / f"{date_key}_short.mp4"
    render_video(content["short_scenes"],short_audio,short_mp4,"portrait",short_attrs)
    short_thumb = short_mp4.with_suffix(".jpg")
    make_thumbnail(content.get("thumbnail_text") or content["short_title"],short_thumb)
    short_desc = content.get("short_description","") + "\n\nSources:\n" + "\n".join(content.get("sources",[]))
    short_desc = add_pexels_attribution(short_desc,short_attrs)

    youtube = youtube_service()
    playlist_ids = ensure_playlists(youtube,state)
    date_record = state.setdefault("published_dates",{}).setdefault(date_key,{})
    # Long upload
    if not date_record.get("long_video_id"):
        publish_at = next_publish_time(LONG_HOUR)
        long_id = upload_video(
            youtube,long_mp4,content["long_title"],long_desc,
            content.get("tags",[]),publish_at,
            playlist_ids.get(PLAYLISTS.get(content.get("category"),"Amazing Science Facts"))
        )
        date_record["long_video_id"] = long_id
        date_record["long_publish_at"] = publish_at
        save_state(state)
    # Short upload
    if not date_record.get("short_video_id"):
        publish_at = next_publish_time(SHORT_HOUR)
        short_id = upload_video(
            youtube,short_mp4,content["short_title"],short_desc,
            content.get("tags",[]),publish_at,playlist_ids.get("Useful Pills AI Shorts")
        )
        date_record["short_video_id"] = short_id
        date_record["short_publish_at"] = publish_at
        save_state(state)

    state.setdefault("recent_topics",[]).append(topic)
    state["recent_topics"] = state["recent_topics"][-60:]
    date_record["topic"] = topic
    date_record["category"] = content.get("category")
    save_state(state)
    log(f"Completed daily production for {date_key}.")

if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv)>1 else "run"
    if command == "validate":
        validate()
    elif command == "run":
        validate()
        create_daily()
    else:
        raise SystemExit("Usage: python pipeline.py [validate|run]")
