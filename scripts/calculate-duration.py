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

import json
import argparse

def calculate_audio_hours(manifest_path:str):
    """
    Calculates the total number of audio hours in a manifest file.

    Args:
        manifest_path (str): Path to the manifest file.

    Returns:
        None
    """
    total_duration_seconds = 0.0

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = [json.loads(line.strip()) for line in f] if manifest_path.endswith('.jsonl') else json.load(f)

    for entry in manifest:
        total_duration_seconds += entry.get('duration', 0.0)

    total_hours = total_duration_seconds / 3600  # Convert seconds to hours

    print(f"Total audio duration: {total_hours:.2f} hours")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Caluclate the total duration of audio files in a manifest.")
    parser.add_argument("--manifest_path", required=True, help="Path to the manifest file (json or jsonl)")

    args = parser.parse_args()
    calculate_audio_hours(args.manifest_path)
