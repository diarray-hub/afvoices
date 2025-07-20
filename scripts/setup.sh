#!/bin/bash

# Usage:
# ./mount_gcs_assist.sh <credential_path> <assist_id> <mount_point>
#
# Example:
# ./mount_gcs_assist.sh path/to/gcsfuse-access.key.json assistN path/to/mount_point

set -e

if [[ $# -ne 4 ]]; then
    echo "Usage: $0 <bucket_name> <credential_path> <assist_id> <mount_point>"
    echo "  <assist_dir> must be one of: assist1, assist2, assist3"
    exit 1
fi

BUCKET_NAME="$1"
CRED_PATH="$2"
ASSIST_DIR="$3"
MOUNT_POINT="$4"

if [[ "$ASSIST_DIR" != "assist1" && "$ASSIST_DIR" != "assist2" && "$ASSIST_DIR" != "assist3" ]]; then
    echo "Error: <assist_id> must be assist1, assist2, or assist3"
    exit 2
fi

# Export the path to the GCS credentials as an Env variable
export GOOGLE_APPLICATION_CREDENTIALS="$CRED_PATH"

mkdir -p "$MOUNT_POINT"

echo "Mounting gs://$BUCKET_NAME/$ASSIST_DIR to $MOUNT_POINT using credentials $CRED_PATH ..."

# Mount the cloud storage bucket to the local directory
gcsfuse --implicit-dirs --only-dir "$ASSIST_DIR" "$BUCKET_NAME" "$MOUNT_POINT"

echo "Mount successful!"

### Unmount it with this command
# fusermount3 -u MOUNT_POINT

### If your terminal fall into an unterminated WAIT (after losing internet connection for instance)
### and you cannot unmount the mount point because it's busy, try killing the processes that occupy it or rebooting your machines