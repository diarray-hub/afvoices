from __future__ import annotations
import argparse
import json
import os
import shutil
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import concurrent.futures as cf
import sys
import time
import threading

LOCK = threading.Lock()

from google.cloud import storage
import torchaudio
from silero_vad import load_silero_vad, get_speech_timestamps

from sharable import make_public_or_token_url, write_excel_from_manifest

# ---------------- helpers ----------------

def list_wav_blobs(bucket_name: str, prefix: str) -> List[str]:
    client = storage.Client()
    matched: List[str] = []
    for blob in client.list_blobs(bucket_name, prefix=prefix):
        if blob.name.endswith("/") or getattr(blob, "size", 0) == 0:
            continue
        if blob.name.lower().endswith(".wav"):
            matched.append(blob.name)
    return matched

def ms(n_samples: int, sr: int) -> int:
    return int(1000.0 * n_samples / sr)

def blob_exists(bucket, blob_name: str, client: storage.Client) -> bool:
    b = bucket.blob(blob_name)
    try:
        return b.exists(client=client)
    except Exception:
        return False

# ---------------- safe operations ----------------

def safe_download_blob(blob, dest: str, timeout: float, retries: int = 5):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            blob.download_to_filename(dest, timeout=timeout)
            return
        except Exception as e:
            last_exc = e
            time.sleep(0.5 * (attempt + 1))
    raise last_exc

def safe_save_waveform(path: Path, waveform, sr: int, retries: int = 5):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            torchaudio.save(str(path), waveform, sr)
            return
        except Exception as e:
            last_exc = e
            time.sleep(0.2 * (attempt + 1))
    raise last_exc

# ---------------- process one audio ----------------

def process_one_audio(
    bucket_name: str,
    object_name: str,
    upload_prefix: str,
    min_duration: float,
    max_duration: float,
    vad_sample_rate: int,
    download_timeout: float,
    no_gcs: bool,
    lock: threading.Lock,
) -> Tuple[str, str, Optional[List[Dict[str, Any]]], Optional[str]]:
    """Process single audio end-to-end: download, VAD, split, save/upload shorts, TSV, transcribe, return manifest."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)

    try:
        basename = os.path.splitext(os.path.basename(object_name))[0]
        audio_dir = Path("workspace") / basename
        short_dir = audio_dir / "shorts"
        tsv_path = audio_dir / f"{basename}.tsv"
        manifest_path = audio_dir / f"{basename}.jsonl"

        with lock:
            short_dir.mkdir(parents=True, exist_ok=True)
            # audio_dir.mkdir(parents=True, exist_ok=True)

        local_wav = audio_dir / "source.wav"

        # download source
        try:
            safe_download_blob(blob, str(local_wav), timeout=download_timeout, retries=2)
        except Exception as e:
            tb = traceback.format_exc()
            return object_name, "ERROR", None, f"download_error: {repr(e)}\n{tb}"

        if not local_wav.exists() or local_wav.stat().st_size == 0:
            return object_name, "ERROR", None, f"download_error: zero-size file {local_wav}"

        # load waveform
        try:
            waveform, orig_sr = torchaudio.load(str(local_wav))
        except Exception as e:
            tb = traceback.format_exc()
            return object_name, "ERROR", None, f"torchaudio_load_error: {repr(e)}\n{tb}"

        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        orig_sr = int(orig_sr)

        if orig_sr != vad_sample_rate:
            waveform = torchaudio.transforms.Resample(orig_sr, vad_sample_rate)(waveform)

        vad_model = load_silero_vad()
        speech_timestamps = get_speech_timestamps(waveform[0], vad_model, sampling_rate=vad_sample_rate)
        sr_ratio = orig_sr / vad_sample_rate

        manifest_items: List[Dict[str, Any]] = []

        with open(tsv_path, "w", encoding="utf-8") as tv:
            tv.write("segment_name\ttype\tstart_sec\tend_sec\tduration_sec\n")

            for i, ts in enumerate(speech_timestamps):
                start_16k, end_16k = ts["start"], ts["end"]
                start_orig = int(start_16k * sr_ratio)
                end_orig = int(end_16k * sr_ratio)
                seg_sec = (end_orig - start_orig) / orig_sr

                splits = []
                if seg_sec > max_duration:
                    num_subsegs = int(seg_sec // max_duration) + 1
                    for j in range(num_subsegs):
                        s = start_orig + int(j * max_duration * orig_sr)
                        e = min(start_orig + int((j + 1) * max_duration * orig_sr), end_orig)
                        splits.append((s, e))
                else:
                    splits = [(start_orig, end_orig)]

                for k, (s, e) in enumerate(splits):
                    dur = (e - s) / orig_sr
                    regular_seg_name = f"{basename}_seg_{i}_{k}.wav"

                    if dur >= min_duration:
                        dest_obj = os.path.join(upload_prefix.rstrip("/"), basename, regular_seg_name)
                        if blob_exists(bucket, dest_obj, client):
                            try:
                                bucket.blob(dest_obj).delete(client=client)
                                print(f"[info] deleted mistaken regular blob: gs://{bucket_name}/{dest_obj}", file=sys.stderr)
                            except Exception as e:
                                tb = traceback.format_exc()
                                return object_name, "ERROR", None, f"delete_regular_error: {repr(e)}\n{tb}"
                        tv.write(f"{regular_seg_name}\tregular\t{round(s/orig_sr,3)}\t{round(e/orig_sr,3)}\t{round(dur,3)}\n")
                        continue

                    start_ms_val, end_ms_val = ms(s, orig_sr), ms(e, orig_sr)
                    short_name = f"{basename}_short_seg_{start_ms_val}_{end_ms_val}.wav"
                    short_path = short_dir / short_name

                    # save with retry
                    try:
                        safe_save_waveform(short_path, waveform[:, s:e], orig_sr)
                    except Exception as e:
                        tb = traceback.format_exc()
                        return object_name, "ERROR", None, f"save_segment_error: {repr(e)}\n{tb}"

                    tv.write(f"{short_name}\tshort\t{round(s/orig_sr,3)}\t{round(e/orig_sr,3)}\t{round(dur,3)}\n")

                    # upload to GCS
                    dest_obj = os.path.join(upload_prefix.rstrip("/"), basename, short_name)
                    try:
                        bucket.blob(dest_obj).upload_from_filename(str(short_path), timeout=download_timeout)
                    except Exception as e:
                        tb = traceback.format_exc()
                        return object_name, "ERROR", None, f"upload_short_error: {repr(e)}\n{tb}"

                    if not no_gcs:
                        try:
                            public_url = make_public_or_token_url(client, bucket_name, dest_obj)
                        except Exception:
                            public_url = f"gs://{bucket_name}/{dest_obj}"
                    else:
                        public_url = f"gs://{bucket_name}/{dest_obj}"

                    manifest_items.append({
                        "audio_gs": f"gs://{bucket_name}/{dest_obj}",
                        "audio_filepath": str(short_path),
                        "public_url": public_url,
                        "duration": round(dur, 3),
                    })

        # save per-audio manifest locally + upload
        try:
            with open(manifest_path, "w", encoding="utf-8") as mf:
                for it in manifest_items:
                    mf.write(json.dumps(it, ensure_ascii=False) + "\n")

            dest_manifest_obj = os.path.join("short-manifests", basename[-13:], f"{basename}.jsonl")
            bucket.blob(dest_manifest_obj).upload_from_filename(str(manifest_path))
        except Exception as e:
            tb = traceback.format_exc()
            return object_name, "ERROR", None, f"upload_manifest_error: {repr(e)}\n{tb}"

        # upload TSV
        try:
            dest_tsv_obj = os.path.join("tsv_timestamps", basename[-13:], f"{basename}.tsv")
            bucket.blob(dest_tsv_obj).upload_from_filename(str(tsv_path), timeout=download_timeout)
        except Exception as e:
            tb = traceback.format_exc()
            return object_name, "ERROR", None, f"upload_tsv_error: {repr(e)}\n{tb}"

        # cleanup: remove only source and short segments
        try:
            if short_dir.exists():
                shutil.rmtree(short_dir)
            if local_wav.exists():
                local_wav.unlink()
        except Exception:
            pass

        return object_name, "OK", manifest_items, None

    except Exception as e:
        tb = traceback.format_exc()
        return object_name, "ERROR", None, f"process_error: {repr(e)}\n{tb}"

# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser(description="Process short segments + TSVs with retries.")
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--prefix", default="validated/")
    ap.add_argument("--upload-prefix", default="short_segments/")
    ap.add_argument("--out-jsonl", required=True)
    ap.add_argument("--out-xlsx", default=None)
    ap.add_argument("--concurrency", type=int, default=max(4, os.cpu_count() or 8))
    ap.add_argument("--min-duration", type=float, default=1.0)
    ap.add_argument("--max-duration", type=float, default=30.0)
    ap.add_argument("--vad-sample-rate", type=int, default=16000)
    ap.add_argument("--download-timeout", type=float, default=15.0)
    ap.add_argument("--no-gcs", action="store_true")
    args = ap.parse_args()

    out_manifest = Path(args.out_jsonl)
    out_manifest.parent.mkdir(parents=True, exist_ok=True)
    Path("workspace").mkdir(exist_ok=True)
    
    print(f"[info] manifest will be written to: {out_manifest.resolve()}", file=sys.stderr)
    all_sources = list_wav_blobs(args.bucket, args.prefix)
    print(f"[info] total wavs: {len(all_sources)} | concurrency: {args.concurrency}", file=sys.stderr)

    jobs = [
        (
            args.bucket,
            name,
            args.upload_prefix,
            args.min_duration,
            args.max_duration,
            args.vad_sample_rate,
            args.download_timeout,
            args.no_gcs,
            LOCK,
        )
        for name in all_sources
    ]

    all_manifest_items: List[Dict[str, Any]] = []
    errors = 0
    processed = 0

    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for (src_name, status, items, err) in ex.map(lambda p: process_one_audio(*p), jobs):
            if status != "OK" or items is None:
                errors += 1
                print(f"[error] {src_name}: {err}", file=sys.stderr)
                continue
            all_manifest_items.extend(items)
            processed += 1

    # Write final concatenated manifest
    try:
        tmp_manifest = out_manifest.with_suffix(out_manifest.suffix + ".tmp")
        with open(tmp_manifest, "w", encoding="utf-8") as mf:
            for it in all_manifest_items:
                out_item = {
                    "semi-label": it.get("text", ""),
                    "duration": it.get("duration"),
                    "audio_filepath": it.get("public_url") if not args.no_gcs else it.get("audio_gs"),
                }
                mf.write(json.dumps(out_item, ensure_ascii=False) + "\n")
        tmp_manifest.replace(out_manifest)
        print(f"[info] wrote manifest at {out_manifest.resolve()}", file=sys.stderr)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[fatal] failed to write manifest: {repr(e)}\n{tb}", file=sys.stderr)
        exit(2)

    print(f"[done] processed={processed} errors={errors} wrote {len(all_manifest_items)} short-segment items → {out_manifest}", file=sys.stderr)

    if args.out_xlsx:
        print("[xlsx] building xlsx...", file=sys.stderr)
        write_excel_from_manifest(out_manifest, Path(args.out_xlsx))
        print("[xlsx] done", file=sys.stderr)

if __name__ == "__main__":
    main()
