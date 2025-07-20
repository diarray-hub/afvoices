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
import os
from urllib.parse import quote

GCS_BASE_URL = "https://storage.googleapis.com/"

def export_manifest_with_gcs(manifest_path: str, gcs_bucket_name: str, root_folder: str):
    """
    Export a new manifest where each audio_filepath is replaced with its GCS public/download URL.
    Args:
        manifest_path (str): Path to the original manifest.
        out_path (str): Path to save the exported manifest.
        gcs_bucket_name (str): The GCS bucket name (e.g. "my-bucket")
    """
    gcs_bucket_path = GCS_BASE_URL + gcs_bucket_name

    # Detect .jsonl or .json
    with open(manifest_path, 'r', encoding='utf-8') as f:
        if manifest_path.endswith('.jsonl'):
            entries = [json.loads(line) for line in f if line.strip()]
        else:
            entries = json.load(f)

    # Convert each audio_filepath to GCS URL
    for entry in entries:
        # Normalize path and URL encode for spaces, etc
        rel_path = os.path.relpath(entry['audio_filepath'])
        gcs_path = quote(os.path.join(root_folder, rel_path))

        # Remove leading ./ or / if present (for clean URL join)
        if gcs_path.startswith("./"):
            gcs_path = gcs_path[2:]
        elif gcs_path.startswith("/"):
            gcs_path = gcs_path[1:]
        entry['audio_filepath'] = gcs_bucket_path.rstrip("/") + "/" + gcs_path

    # Save
    basename = os.path.basename(manifest_path)
    out_dir = "exportable"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, basename)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        if out_path.endswith('.jsonl'):
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        else:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"Exported manifest with GCS URLs to {out_path}")

def main():
    parser = argparse.ArgumentParser(description="Export manifest with GCS URLs for audio files.")
    parser.add_argument("--manifest_path", type=str, required=True, help="Path to the original manifest (json or jsonl)")
    parser.add_argument("--gcs_bucket_name", type=str, required=True, help="GCS bucket name, e.g. my-bucket")
    parser.add_argument("--root_folder", type=str, help="assistN folder name, e.g. 'assist1'")

    args = parser.parse_args()
    export_manifest_with_gcs(args.manifest_path,  args.gcs_bucket_name, args.root_folder)

if __name__ == "__main__":
    main()
