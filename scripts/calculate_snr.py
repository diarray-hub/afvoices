import argparse, sys, os, csv
import numpy as np
import torch, torchaudio
from silero_vad import load_silero_vad, get_speech_timestamps

# ─── config ───────────────────────────────────────────────────────────
VAD_SR = 16_000
VAD = load_silero_vad()
EPS = 1e-12

def rms_db(x: np.ndarray) -> float:
    x = x.astype(np.float64)
    x = x - x.mean()              # remove DC
    return 20 * np.log10(np.sqrt(np.mean(x**2) + EPS))

def _intervals_to_mask(intervals, n, sr, guard_s: float):
    """(start,end) sample intervals → boolean mask with guard padding."""
    g = int(round(guard_s * sr))
    m = np.zeros(n, dtype=bool)
    for s, e in intervals:
        s = max(0, s - g); e = min(n, e + g)
        if s < e:
            m[s:e] = True
    return m

def _merge_short_islands(mask: np.ndarray, min_len: int):
    """Remove short True islands in a boolean mask (in-place)."""
    n = len(mask); i = 0
    while i < n:
        if mask[i]:
            j = i + 1
            while j < n and mask[j]:
                j += 1
            if (j - i) < min_len:
                mask[i:j] = False
            i = j
        else:
            i += 1
    return mask

def _get_speech_intervals(x: np.ndarray, sr: int):
    x_t = torch.from_numpy(x)
    if sr != VAD_SR:
        x_t = torchaudio.functional.resample(x_t, sr, VAD_SR)
    ts = get_speech_timestamps(x_t, VAD, sampling_rate=VAD_SR)
    ratio = sr / float(VAD_SR)
    return [(int(t['start'] * ratio), int(t['end'] * ratio)) for t in ts]

def categorize_snr(snr_db: float) -> str:
    if snr_db < 0:        return "Very low SNR"
    if snr_db < 5:        return "Low SNR"
    if snr_db < 15:       return "Medium SNR"
    if snr_db < 25:       return "High SNR"
    return "Very high SNR"

def process_audio_vad(file_path: str,
                      guard_ms: int = 20,
                      min_noise_ms: int = 100,
                      noise_floor_db: float = -60.0):
    """
    Returns: (sample_rate, speech_db, noise_db, snr_db)
    Method: VAD-based global SNR (speech from VAD regions, noise from non-speech).
    """
    wav, sr = torchaudio.load(file_path)     # [C, T]
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    x = wav.squeeze(0).numpy()
    n = x.shape[0]

    speech_iv = _get_speech_intervals(x, sr)
    speech_mask = _intervals_to_mask(speech_iv, n, sr, guard_ms / 1000.0)

    noise_mask = ~speech_mask
    # Drop tiny non-speech islands (boundary breaths/clicks)
    min_len = int((min_noise_ms / 1000.0) * sr)
    _merge_short_islands(noise_mask, min_len)

    # Fallbacks
    xs = x[speech_mask]
    xn = x[noise_mask]
    if xs.size == 0:   # no VAD → treat whole as speech (rare)
        xs = x
    if xn.size == 0:   # no non-speech → estimate from low-percentile RMS
        frame = max(1, int(0.025 * sr))
        hop   = max(1, int(0.010 * sr))
        rms = []
        for a in range(0, n - frame + 1, hop):
            f = x[a:a+frame]; f = f - f.mean()
            rms.append(np.sqrt(np.mean(f**2) + EPS))
        if rms:
            p20 = np.percentile(rms, 20)
            xn = x[np.abs(x) <= p20]
    if xn.size == 0:   # still nothing → clamp to tiny noise floor
        xn = np.random.normal(scale=10**(noise_floor_db/20), size=sr//10)

    speech_db = rms_db(xs)
    noise_db  = rms_db(xn)
    snr_db    = speech_db - noise_db
    return sr, speech_db, noise_db, snr_db

def parse_inputs(inputs):
    # Accept: space-separated and/or comma-separated
    files = []
    for item in inputs:
        files.extend([p for p in (s.strip() for s in item.split(",")) if p])
    return files

def main():
    ap = argparse.ArgumentParser(description="Compute VAD-based global SNR for audio files and output CSV.")
    ap.add_argument("-i", nargs="+", help="Audio files (space and/or comma separated).")
    ap.add_argument("-o", default="-", help="Output CSV path (default: stdout).")
    ap.add_argument("--guard-ms", type=int, default=20, help="Guard padding around speech (ms).")
    ap.add_argument("--min-noise-ms", type=int, default=100, help="Minimum non-speech island length (ms).")
    ap.add_argument("--noise-floor-db", type=float, default=-60.0, help="Fallback noise floor (dB).")
    args = ap.parse_args()

    files = parse_inputs(args.i)
    rows = []

    for f in files:
        if not os.path.exists(f):
            print(f"[warn] file not found: {f}", file=sys.stderr)
            continue
        try:
            sr, s_db, n_db, snr = process_audio_vad(
                f, guard_ms=args.guard_ms, min_noise_ms=args.min_noise_ms, noise_floor_db=args.noise_floor_db
            )
            rows.append([
                os.path.basename(f),
                int(sr),
                f"{s_db:.2f}",
                f"{n_db:.2f}",
                f"{snr:.2f}",
                categorize_snr(snr),
            ])
        except Exception as e:
            print(f"[error] {f}: {e}", file=sys.stderr)

    # write CSV
    header = ["Audio Name", "Sample Rate", "Speech RMS (dB)", "Noise RMS (dB)", "SNR (dB)", "Category"]
    if args.o == "-" or args.o.lower() == "stdout":
        w = csv.writer(sys.stdout)
        w.writerow(header)
        w.writerows(rows)
    else:
        with open(args.o, "w", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            w.writerow(header)
            w.writerows(rows)

if __name__ == "__main__":
    main()
