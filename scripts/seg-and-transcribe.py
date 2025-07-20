"""
Copyright 2025 RobotsMali AI4D Lab.

Licensed under the MIT License; you may not use this file except in compliance with the License.  
You may obtain a copy of the License at:

https://opensource.org/licenses/MIT

Unless required by applicable law or agreed to in writing, software  
distributed under the License is distributed on an "AS IS" BASIS,  
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  
See the License for the specific language governing permissions and  
limitations under the License.
"""

import os
import argparse
import json
import getpass
import torchaudio
from silero_vad import load_silero_vad, get_speech_timestamps
from nemo.collections.asr.models import EncDecHybridRNNTCTCBPEModel

ENGINEER = getpass.getuser()

def segment_audio_with_vad(
    input_path,
    output_dir,
    min_duration=1.0,
    max_duration=30.0,
    vad_sample_rate=16000,
):
    """
    Segments an audio file using Silero VAD. Handles resampling if needed, splits segments as necessary, and returns the segment manifest and base filename.
    Args:
        input_path (str): Path to the input audio file.
        output_dir (str): Directory to save the segmented audio files.
        min_duration (float): Minimum duration for segments (seconds).
        max_duration (float): Maximum duration for segments (seconds).
        vad_sample_rate (int): Sampling rate for the VAD model (default 16kHz).
    Returns:
        tuple: (manifest list, basename)
    """
    waveform, orig_sr = torchaudio.load(input_path)  # waveform: (channels, n_samples)
    print(f"Loaded audio: {input_path}, with original sample rate: {orig_sr}. Beginning segmentation...")

    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)  # Convert to mono

    orig_sr = int(orig_sr)

    # Resample for VAD if needed
    if orig_sr != vad_sample_rate:
        resampler = torchaudio.transforms.Resample(orig_sr, vad_sample_rate)
        vad_waveform = resampler(waveform)
    else:
        vad_waveform = waveform

    # Load Silero VAD model (CPU by default)
    model = load_silero_vad()

    # Silero expects shape [1, n_samples]
    print("Peforming Voice Activity Detection (VAD)...")
    speech_timestamps = get_speech_timestamps(
        vad_waveform[0], model, sampling_rate=vad_sample_rate
    )

    basename = os.path.splitext(os.path.basename(input_path))[0]
    os.makedirs(output_dir, exist_ok=True)
    manifest = []

    # Ratio to map VAD indices back to original
    sr_ratio = orig_sr / vad_sample_rate

    for i, ts in enumerate(speech_timestamps):
        start_16k, end_16k = ts['start'], ts['end']
        # Map to original sampling rate
        start_orig = int(start_16k * sr_ratio)
        end_orig = int(end_16k * sr_ratio)
        seg_samples = end_orig - start_orig
        seg_sec = seg_samples / orig_sr

        # Split long segments if needed
        splits = []
        if seg_sec > max_duration:
            print(f"Found long segment of duration {seg_sec}, splitting based on MAX() and remainings")
            num_subsegs = int(seg_sec // max_duration) + 1
            for j in range(num_subsegs):
                s = start_orig + int(j * max_duration * orig_sr)
                e = min(start_orig + int((j+1) * max_duration * orig_sr), end_orig)
                if (e-s)/orig_sr >= min_duration:
                    splits.append((s, e))
        elif seg_sec >= min_duration:
            splits = [(start_orig, end_orig)]

        for k, (s, e) in enumerate(splits):
            seg_audio = waveform[:, s:e]
            seg_filename = f"{basename}_seg_{i}_{k}.wav"
            seg_path = os.path.join(output_dir, seg_filename)
            torchaudio.save(seg_path, seg_audio, orig_sr)
            duration = (e - s) / orig_sr
            manifest.append({
                "audio_filepath": seg_path,
                "duration": duration,
                "engineer": ENGINEER,
            })

    return manifest, basename

def transcribe_manifest(
    manifest: list,
    manifest_name: str,
    model_name: str = 'RobotsMali/soloni-114m-tdt-ctc-V0',
    decoding: str = 'ctc',
    batch_size: int = 16
):
    """
    Transcribes segmented audio files using a NeMo ASR model and writes a new manifest including predicted text.
    Args:
        manifest (list): List of dictionaries with segment metadata.
        manifest_name (str): Name for the new manifest file.
        model_name (str): NeMo model name to use for ASR.
        decoding (str): Decoding strategy (default 'ctc').
        batch_size (int): Batch size for ASR model inference.
    """
    audios = [entry['audio_filepath'] for entry in manifest]
    model = EncDecHybridRNNTCTCBPEModel.from_pretrained(model_name=model_name)
    model.eval()
    model.summarize()

    if decoding == 'ctc':
        # Retrieve the CTC decoding config
        ctc_decoding_cfg = model.cfg.aux_ctc.decoding
        model.change_decoding_strategy(decoder_type='ctc', decoding_cfg=ctc_decoding_cfg)

    print(f"Begining transcription with: model={model_name}; decoding={decoding} and batch_size={batch_size}")
    hypotheses = model.transcribe(audios, batch_size=batch_size)
    print("Transcription is over, preparing new manifest")

    for index, entry in enumerate(manifest):
        entry['text'] = hypotheses[index].text.capitalize()

    os.makedirs('manifests', exist_ok=True)
    new_manifest_path = os.path.join('manifests', manifest_name)

    with open(new_manifest_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, ensure_ascii=False) + "\n")

    print(f"New manifest saved to: {new_manifest_path}")

def main():
    """
    Main entry point for script. Handles argument parsing, segmentation, and transcription.
    """

    parser = argparse.ArgumentParser(
        description="Segment audio using Silero VAD, with on-the-fly resampling, ASR pre-labeling, and manifest output."
    )
    parser.add_argument("--audio_path", help="Path to input audio file (wav, any rate)")
    parser.add_argument("--output_dir", type=str, default='processed', help="Directory to save audio segments")
    parser.add_argument("--min_duration", type=float, default=1.0, help="Minimum segment duration in seconds")
    parser.add_argument("--max_duration", type=float, default=30.0, help="Maximum segment duration in seconds")
    parser.add_argument("--vad_sample_rate", type=int, default=16000, help="Sample rate for VAD model (default: 16k)")
    parser.add_argument("--model_name", type=str, default='RobotsMali/soloni-114m-tdt-ctc-V0', help="ASR model name")
    parser.add_argument("--decoding", type=str, default='ctc', help="ASR decoding strategy")
    parser.add_argument("--batch_size", type=int, default=16, help="Batch size for ASR inference")

    args = parser.parse_args()
    manifest, basename = segment_audio_with_vad(
        args.audio_path, args.output_dir,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        vad_sample_rate=args.vad_sample_rate
    )

    transcribe_manifest(
        manifest=manifest,
        manifest_name=f"{basename}_manifest.json",
        model_name=args.model_name,
        decoding=args.decoding,
        batch_size=args.batch_size
    )

if __name__ == "__main__":
    main()
