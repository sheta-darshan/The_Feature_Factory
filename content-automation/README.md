# Product Content Automation

Turns 5 client product photos into a full content package automatically:
- N generated product images (studio / lifestyle / festival variants)
- N short vertical reels (image-to-video)
- Captions + hashtags for every piece
- Thumbnails
- Everything zipped into one delivery folder per client

Runs entirely on your PC. You upload photos through a local web page,
the pipeline runs in the background, and you get a finished zip.

## How it works

1. `main.py` — a small FastAPI web app. Open it in a browser on your own
   machine, fill in the client's brief (business name, style, package
   size), upload their 5 photos, hit submit.
2. That creates a "job" (a folder + a status file in `jobs/`).
3. `orchestrator.py` picks up the job and runs three things, two of them
   in parallel:
   - `integrations/image_gen.py` → calls an image API for each photo
   - `integrations/video_gen.py` → calls a video API for each photo
   - `integrations/captions.py` → calls the Claude API once for all captions
4. `assembler.py` uses ffmpeg to add caption text onto the reels, pull a
   thumbnail frame from each, and zip everything into
   `outputs/<job_id>/delivery.zip`.
5. You (or eventually the client) download the zip from the job status
   page.

## What you need to fill in

This scaffold is fully wired end-to-end but the three AI calls in
`integrations/` are stubbed with clear TODOs — you drop in real API
calls once you've picked providers and gotten keys. Recommended to
start with:

- **Images**: any image-editing API that takes a reference photo + a
  text prompt (e.g. Nano Banana Pro, Flux Kontext, Ideogram). All of
  these work the same way: send image + prompt, get image back.
- **Video**: Kling AI's image-to-video API is the best value for
  volume right now (~$0.07/sec, per current market pricing — verify
  on their site since AI video pricing shifts often). Runway Gen-4 is
  the alternative if you want higher control/quality per clip.
- **Captions**: the Anthropic API (Claude) — already wired to give you
  the right shape (JSON in, JSON out), you just need an API key.

Each integration file has one function to fill in. Nothing else in the
project needs to change when you swap providers later — that's the
point of keeping them isolated.

## Setup

```bash
cd content-automation
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Install ffmpeg (used for stitching/captions/thumbnails):
- Windows: `winget install ffmpeg` or download from ffmpeg.org
- Mac: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Run it:

```bash
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000` in your browser.

## Keeping it running in the background

Since it needs to run "always on" on your PC:

- **Windows**: use Task Scheduler to run `uvicorn` at login, or wrap it
  with `pythonw` + NSSM to run as a service.
- **Mac**: use `launchd` with a plist that runs the uvicorn command.
- **Linux**: use a `systemd` service (`ExecStart=venv/bin/uvicorn
  main:app --port 8000`).

Once you're taking real client uploads (not just yourself testing),
you'll want either a static IP + port forwarding, or a tunnel like
Cloudflare Tunnel / ngrok, so a client can upload from their phone
instead of you doing it manually. Not needed for v1 — you can just
run this locally and handle uploads yourself at first.

## Job status and concurrency

Jobs are tracked as JSON files in `jobs/`. The orchestrator processes
one job at a time by default (`MAX_CONCURRENT_JOBS` in `config.py`) —
raise this once you've confirmed your API rate limits can handle it.

## Cost per job (rough, verify current pricing before pricing your packages)

For a 10-reel package (Business tier, ₹5,999):
- 10 images (edit/generate): usually $0.02–0.05 each → ~$0.30–0.50
- 10 reels (~5 sec each) via Kling-class API: ~$0.35/clip → ~$3.50
- Captions (1 LLM call): negligible, well under $0.05

Total AI cost is roughly $4–5 (≈₹350–450) per Business-tier job, leaving
healthy margin against ₹5,999. Video is by far the biggest cost driver —
if you want to trim it, generate fewer/shorter video clips and lean more
on the image package.
