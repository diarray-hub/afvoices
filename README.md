# AFVoices — Bambara 600 h Pre‑processing Pipeline

> **Purpose** · This repo collects the **scripts and helper bash utilities** used by our data‑processing assistants to turn **≈ 600 h of raw Bambara speech stored in Google Cloud Storage (GCS)** into segmented, reviewed, and share‑ready manifests.  Think of it as your *operations manual* – follow it top‑to‑bottom and you will create reproducible, high‑quality data.

---

## 0 · TL;DR

```bash
# 1 · one‑time machine prep (Ubuntu ≥22.04)
./scripts/gcsfuse-install.sh           # install gcsfuse & deps

# 2 · mount a specific folder of the bucket read‑write (each of you already has a working home dir, e.g assist1)
./scripts/setup.sh <bucket> <cred.json> <assist_id> <mount_point> # (e.g mnt)

# 4 · segment + transcribe your newly‑assigned WAVs
python3 scripts/seg-and-transcribe.py  \
        --audio_path ./mnt/raw/path_to_audio.wav

# 5 · manual QC – 25% of segments
python3 scripts/review.py              \
        --manifest_path ./path/to/manifest.jsonl

# 6 · generate another manifest with the (GCS URLs)
python3 scripts/export-manifest.py     \
        --manifest ./path/to/manifest.jsonl \
        --gcs_bucket_name <bucket> --root_folder assistN > manifest_gcs.jsonl
```

*(Swap `assist1` with `assist2/3` depending on who you are.)*

---

## 1 · Repository Layout

```
afvoices/
 ├─ scripts/           # All automation lives here
 │   ├─ seg-and-transcribe.py  # VAD segmentation + Whisper
 │   ├─ review.py      # ncurses‑style 3‑question reviewer
 │   ├─ export-manifest.py     # turn local paths → GCS URLs
 │   ├─ calculate-duration.py  # quick sanity stats on a manifest
 │   ├─ setup.sh       # mount helper (gcsfuse + mkdirs)
 │   └─ gcsfuse-install.sh     # one‑liner installer for gcsfuse
 └─ README.md          # you are here
```

---

## 2 · Prerequisites

| Requirement            | Why                  | Install hint                        |
| ---------------------- | -------------------- | -------------------------------     |
| **Ubuntu 22.04 LTS**   | tested host OS       |                                     |
| **Python ≥ 3.10**      | run the pipeline     | `sudo apt install python3‑venv`     |
| **gcsfuse ≥ 0.46**     | mount the bucket     | `./scripts/gcsfuse-install.sh`      |
| **FFmpeg + SoX**       | resampling & wav ops | `sudo apt install ffmpeg sox`       |
| **requirements.txt**   |  NVIDIA NeMo etc.    | `pip install -r requirements.txt`   |

Create a virtualenv and install Python deps:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3 · Mounting the Cloud Bucket

1. Obtain **service‑account JSON credentials** with read‑write rights.
2. Run `setup.sh`:

   ```bash
   ./scripts/setup.sh <bucket> <cred.json> <assist_id> <mount_point> # (e.g mnt)
   ```

3. **Unmount** with `fusermount -u ./mnt` when done.

> **Tip** – make sure to unmount the bucket before shutting down your machine, just rerun `setup.sh` when you wish to recreate your work environment.

---

## 4 · License

Code is MIT‑licensed © 2025 RobotsMali AI4D Lab.  Audio are under creative common.
