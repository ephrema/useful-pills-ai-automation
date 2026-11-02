# Useful Pills AI — serverless YouTube automation

This starter project automates one educational long video and one Short per day:
topic/research -> script -> Piper narration -> Pexels footage (or generated visual cards)
-> FFmpeg rendering -> thumbnail -> YouTube upload/scheduling -> playlist assignment.

It uses GitHub-hosted runners, not a VPS or self-managed server. The runner is temporary
and is created by GitHub Actions for each scheduled run.

## Important limitations

- "Free as much as possible" is not the same as guaranteed $0. Gemini API free-tier
  availability/limits, GitHub Actions account limits, and third-party quotas can change.
- Standard GitHub-hosted runners are free for public repositories. Private repositories
  consume the plan's included minutes and may incur charges. See GitHub's current billing docs.
- Gemini API free-tier data handling differs from paid tier. Use it only for public
  educational content; never send personal, confidential, or copyrighted private material.
- Pexels API is free subject to its terms and limits. The project adds attribution to descriptions.
- Piper is an open-source local TTS engine. The selected voice model has its own license;
  review the model license before commercial use.
- AI research is not infallible. The system performs a second AI review, but it cannot
  guarantee factual accuracy. This project is configured to publish automatically after
  automated checks. If zero risk is required, human approval is necessary.
- YouTube may require disclosure for realistic AI-generated/altered scenes. This project
  uses stock footage and generated narration, not photorealistic fabricated events.
  Review YouTube's current altered-content rules.
- Repetitive, mass-produced, low-value videos may not qualify for monetization. Vary the
  substance, examples, narrative, and visuals. Do not copy BRIGHT SIDE scripts or assets.

## Architecture

- GitHub Actions: scheduler and temporary compute.
- Gemini API: grounded research, scripts, titles, descriptions, scene plans and quality review.
- Piper TTS: local narration generation on the runner.
- Pexels API: stock footage; if unavailable, generated motion-card visuals are used.
- FFmpeg: renders 16:9 long video and 9:16 Short.
- YouTube Data API: resumable upload, thumbnails, playlists, scheduled publication.
- `state/history.json`: remembers published topics and prevents duplicate daily uploads.

No VPS, Docker host, or always-on server is required.

## 1. Create accounts

1. Create/sign in to a GitHub account.
2. Create a **public** repository named `useful-pills-ai-automation` if you want GitHub-hosted
   standard runner usage to be free. A public repo exposes source code and state files, not
   GitHub Secrets. Never commit credentials.
3. Create a Gemini API key at https://aistudio.google.com/app/apikey.
4. Request a Pexels API key at https://www.pexels.com/api/.
5. Create a Google Cloud project and enable **YouTube Data API v3**.
6. Configure OAuth consent for your own Google account/channel.
7. Create OAuth client credentials of type **Desktop app** and download the client JSON.

## 2. Authorize YouTube once

On your own Windows/Mac/Linux computer (not on GitHub):

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements-auth.txt
python auth_youtube.py client_secret.json
```

A browser opens. Sign in with the Google account that owns/manages the channel and approve
the YouTube permissions. The script prints the refresh token and client ID. Copy these
values into GitHub Secrets. Do not share them.

**OAuth consent warning:** Do not leave an external OAuth app in "Testing" if you need a
long-lived refresh token. Google documents that refresh tokens issued to external test
users can expire after seven days. Publish the consent app to Production as appropriate.
Verification may be required depending on the scopes and usage. See Google's OAuth docs.

## 3. Add GitHub repository secrets

Repository -> Settings -> Secrets and variables -> Actions -> New repository secret:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | Gemini API key |
| `PEXELS_API_KEY` | Pexels API key (optional; fallback visuals work without it) |
| `YOUTUBE_CLIENT_ID` | OAuth desktop client ID |
| `YOUTUBE_CLIENT_SECRET` | OAuth desktop client secret |
| `YOUTUBE_REFRESH_TOKEN` | Refresh token printed by `auth_youtube.py` |

Never put these in source files, Sheets, commit history, or chat.

## 4. Add the project files

Upload all files from this project into the root of your GitHub repository, preserving
folders. Commit to the `main` branch.

The workflow runs daily at 02:00 UTC (05:00 Addis Ababa time). It creates:
- one 6–8 minute landscape video, scheduled for 18:00 Addis Ababa time;
- one 35–55 second vertical Short, scheduled for 20:00 Addis Ababa time.

GitHub scheduled workflows can start late. The script calculates future publication times.
Change these values using repository variables if needed:
- `LONG_PUBLISH_HOUR` (default 18)
- `SHORT_PUBLISH_HOUR` (default 20)
- `TIMEZONE` (default Africa/Addis_Ababa)
- `GEMINI_MODEL` (default gemini-2.5-flash)

## 5. First test — do not immediately run daily

1. Add all secrets.
2. Open Actions -> Useful Pills AI Daily Production.
3. Select Run workflow.
4. Watch the logs.
5. The first run can take time because it installs FFmpeg/Piper and downloads the voice model.
6. Confirm both videos appear in YouTube Studio as scheduled/private.
7. Confirm thumbnails and playlists.
8. Only then leave the daily schedule enabled.

The workflow uses scheduled private uploads. YouTube makes them public at the requested
future time. If upload processing is not complete by then, publication can be delayed.

## 6. Adjust content categories and playlists

The prompt rotates among:
- Science and amazing facts
- Psychology and human behavior
- Life hacks and useful knowledge
- History and mysteries
- Brain games and riddles
- Technology and artificial intelligence
- Money and business knowledge
- Nature and amazing discoveries

The code creates these playlists if they do not already exist:
1. Amazing Science Facts
2. Psychology Explained
3. Technology and Artificial Intelligence
4. History and Mysteries
5. Brain Games and Riddles
6. Life Hacks and Useful Tips
7. Money and Business Knowledge
8. Nature and Amazing Discoveries
9. Useful Pills AI Shorts

## 7. Quality and safety controls

The generator:
- asks Gemini to use Google Search grounding;
- asks for source URLs and fact-checks the draft in a separate pass;
- rejects malformed JSON, short scripts, missing scenes, and failed review;
- avoids topics already published recently;
- includes Pexels attribution when stock footage is used;
- does not use copyrighted music;
- uploads as scheduled private videos and stores YouTube IDs in state.

Automated checks are not a guarantee. For medical, legal, financial, political, emergency,
or other high-impact topics, change the prompt to exclude them or require manual review.
The current prompt excludes personalized medical/legal/financial advice and sensational
misinformation.

## 8. Troubleshooting

### Gemini 429 / quota
Wait for quota reset, reduce frequency, or use a paid tier. Do not create multiple API keys
to bypass provider limits.

### Gemini model not found
Change the `GEMINI_MODEL` repository variable to a model currently enabled for your API key.

### Pexels 401 / 429
Check the key and current quota. The workflow falls back to generated visual cards if footage
search fails, but the final video will be less visually rich.

### Piper download or voice error
Check GitHub runner network access and the Piper voice model URL. The workflow caches the
model between runs when GitHub cache is available.

### YouTube invalid_grant
Re-authorize with `auth_youtube.py`, update the refresh token secret, and ensure OAuth consent
is not left in Testing. Check whether access was revoked or the token was rotated.

### YouTube upload quota
The default YouTube Data API quota is sufficient for two video uploads daily in normal cases,
but playlist and thumbnail operations also consume quota. Check Google Cloud Console quotas.

### Video processing or upload failure
The state file is committed after each successful upload. A rerun skips a video already
uploaded for that date and retries the missing item.

## 9. Stop automation

Repository -> Actions -> Useful Pills AI Daily Production -> ... -> Disable workflow.
You can also remove the `schedule` section from `.github/workflows/daily.yml`.

## 10. Official references

- Apps Script quotas (not used as the video renderer): https://developers.google.com/apps-script/guides/services/quotas
- Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing
- YouTube upload API: https://developers.google.com/youtube/v3/docs/videos/insert
- YouTube API quota: https://developers.google.com/youtube/v3/determine_quota_cost
- Google OAuth: https://developers.google.com/identity/protocols/oauth2
- GitHub Actions billing: https://docs.github.com/en/actions/concepts/billing-and-usage
- Pexels API: https://www.pexels.com/api/documentation/
- YouTube monetization policy: https://support.google.com/youtube/answer/1311392
- YouTube altered/synthetic content disclosure: https://support.google.com/youtube/answer/14328491
