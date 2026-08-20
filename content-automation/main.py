"""
The web app you open in your browser to run jobs.

Routes:
  GET  /                 upload form
  POST /submit           creates a job, kicks off the pipeline in the background
  GET  /job/{job_id}     status page (auto-refreshes while processing)
  GET  /download/{job_id} downloads the finished delivery.zip
  GET  /jobs              list of all past jobs
"""
import shutil
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import UPLOADS_DIR, PACKAGES
from job_store import new_job_id, create_job, load_job, list_jobs, update_job
from orchestrator import run_job

app = FastAPI(title="Product Content Automation")
templates = Jinja2Templates(directory="static")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    return templates.TemplateResponse(
        "upload.html", {"request": request, "packages": PACKAGES}
    )


@app.post("/submit")
async def submit(
    request: Request,
    business_name: str = Form(...),
    business_type: str = Form(...),
    product_name: str = Form(""),
    package: str = Form(...),
    photos: list[UploadFile] = File(...),
):
    job_id = new_job_id()
    job_upload_dir = UPLOADS_DIR / job_id
    job_upload_dir.mkdir(parents=True, exist_ok=True)

    photo_paths = []
    for i, photo in enumerate(photos):
        dest = job_upload_dir / f"photo_{i+1}{Path(photo.filename).suffix or '.jpg'}"
        with dest.open("wb") as f:
            shutil.copyfileobj(photo.file, f)
        photo_paths.append(str(dest))

    pkg = PACKAGES.get(package, PACKAGES["starter"])
    job = create_job(job_id, {
        "business_name": business_name,
        "business_type": business_type,
        "product_name": product_name,
        "package": package,
        "n_images": pkg["images"],
        "n_reels": pkg["reels"],
        "photo_paths": photo_paths,
    })

    # Fire and forget: FastAPI will run this in the background while
    # the response returns immediately to the browser.
    import asyncio
    asyncio.create_task(run_job(job_id, job))

    return RedirectResponse(f"/job/{job_id}", status_code=303)


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_status(request: Request, job_id: str):
    job = load_job(job_id)
    if job is None:
        return HTMLResponse("Job not found", status_code=404)
    return templates.TemplateResponse("status.html", {"request": request, "job": job})


@app.get("/download/{job_id}")
async def download(job_id: str):
    job = load_job(job_id)
    if job is None or not job.get("delivery_zip"):
        return HTMLResponse("Not ready", status_code=404)
    return FileResponse(job["delivery_zip"], filename=f"{job['business_name']}_content.zip")


@app.get("/jobs", response_class=HTMLResponse)
async def all_jobs(request: Request):
    return templates.TemplateResponse("jobs.html", {"request": request, "jobs": list_jobs()})
