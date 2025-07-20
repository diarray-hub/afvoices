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

import argparse
import json
import random
import os
import sys
import time
from datetime import datetime
import getpass
from typing import List
import questionary

REVIEWER = getpass.getuser()

try:
    import sounddevice as sd
    import soundfile as sf
except ImportError:
    print("Please install sounddevice and soundfile: pip install sounddevice soundfile")
    sys.exit(1)

REVIEW_QUESTIONS = [
    ("segmentation_accuracy", "How accurate is the segmentation? (doesn't cut speech)", ["bad", "decent", "good"]),
    ("recording_quality", "Quality of the recording (audibility, background noise, code switching)", ["bad", "decent", "good"]),
    ("transcription_quality", "Quality of the transcription", ["bad", "decent", "good"]),
]

def load_manifest(manifest_path: str) -> List[dict]:
    """Load manifest from JSON or JSONL file."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        # Handle both json and jsonl
        if manifest_path.endswith('.jsonl'):
            return [json.loads(line) for line in f if line.strip()]
        else:
            return json.load(f)

def play_audio(filepath: str):
    """Play an audio file using sounddevice and soundfile."""
    data, samplerate = sf.read(filepath, dtype='float32')
    sd.play(data, samplerate)
    sd.wait()

def review_segments(manifest_path: str, sample_ratio: float = 0.25, seed: int = 42):
    """Review a random 30% sample of segments from manifest and collect feedback interactively (dropdown UI)."""

    segments = load_manifest(manifest_path)
    if not segments:
        print("Manifest is empty!")
        return
    num_samples = max(1, int(len(segments) * sample_ratio))
    random.seed(seed)
    to_review = random.sample(segments, num_samples)

    print(f"Loaded {len(segments)} segments. {num_samples} will be reviewed.")
    results = []
    completed = False
    start_time = time.time()

    try:
        for idx, segment in enumerate(to_review):
            print(f"--- Reviewing segment {idx+1}/{num_samples} ---")
            print(f"Audio: {segment['audio_filepath']}")
            print(f"Duration: {segment.get('duration', 'N/A')}s")
            print(f"***Transcription: {segment.get('text', '[no transcription]')}***")
            # Always play audio at the start of each segment
            play_audio(segment['audio_filepath'])
            review = {
                'segment_index': idx,
                'audio_filepath': segment['audio_filepath'],
                'duration': segment.get('duration'),
                'engineer': segment.get('engineer'),
                'transcription': segment.get('text', None),
            }
            for key, q, opts in REVIEW_QUESTIONS:
                while True:
                    ans = questionary.select(
                        f"{q} (Use ↑/↓ and Enter to select. Choose '[r] Relisten' to play again.)",
                        choices=opts + ["[r] Relisten"]
                    ).ask()
                    if ans == "[r] Relisten":
                        play_audio(segment['audio_filepath'])
                        continue
                    else:
                        review[key] = ans
                        break
            results.append(review)

        completed = True
    except KeyboardInterrupt:
        print("\nReview interrupted by user.")
    finally:
        end_time = time.time()
        review_meta = {
            'reviewer': REVIEWER,
            'datetime': datetime.now().isoformat(),
            'manifest_reviewed': manifest_path,
            'num_segments': len(segments),
            'num_reviewed': len(results),
            'total_to_review': num_samples,
            'completed': completed,
            'time_elapsed_seconds': int(end_time - start_time)
        }
        out_data = {
            'meta': review_meta,
            'results': results
        }
        
        os.makedirs("reviews", exist_ok=True)
        basename = os.path.splitext(os.path.basename(manifest_path))[0]

        out_path = os.path.join("reviews", basename + '.json')

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2, ensure_ascii=False)
            print(f"\nReview session saved to {out_path}")

            if not completed:
                print("Session marked as incomplete (user exited before 100%).")

def main():
    parser = argparse.ArgumentParser(description="Randomly sample segments for manual review and collect feedback interactively.")
    parser.add_argument("--manifest_path", required=True, help="Path to the manifest file (json or jsonl)")
    parser.add_argument("--sample_ratio", type=float, default=0.25, help="Proportion of segments to review (default 0.25)")
    args = parser.parse_args()
    
    review_segments(args.manifest_path, sample_ratio=args.sample_ratio)

if __name__ == "__main__":
    main()
