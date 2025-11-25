# Afvoices — Bambara 600 h Pre‑processing Pipeline

This repo collects the **helper utilities** used by our data‑processing team to transform the **626 hours** of raw Bambara speech that we have recorded as part of the African Next Voices (ANV) project into segmented, pre-labeled and share‑ready manifests.  Think of it as our audio preprocessing *operations manual*.

We share dev-versions of the code, meaning the scripts in this repository are the first implementation and tests of our preprocessing pipeline using Google Cloud Storage FUSE, the code is therefore not optimized for large scale processing but useful if you wish to reproduce the work or have a better understanding of the different components of our pipeline.

We have made the raw recordings and their associated metadata and segmentation timestamps publicly available for download, you can download and reconstitute the dataset with the links in manifest/raw-and-meta-600.jsonl. You can also download our [SNR evaluation](https://storage.googleapis.com/africa-voice-mali.firebasestorage.app/afvoices/snr.csv) for 612 hours that we processed.

---

## 2 · The Hugging Face Dataset

We have processed about 612 hours of those recordings, 159 for which we have corrected the automatically generated transcriptions. We release this segmented version of the dataset on hugging face. A total of 423 hours, for more details please check the dataset card on HF: [RobotsMali/afvoices](https://huggingface.co/datasets/RobotsMali/afvoices).

### Use this dataset

```python

from datasets import load_dataset

ds = load_dataset("RobotsMali/afvoices", "human-corrected") # or "model-annotated" / "short"
```

If you want to reconstruct the HF dataset with the original file names you can use the [download_from_gcs](./scripts/download_from_gcs.py) script and the jsonl files in the manifest folder of this repo to download the segments from GSC.

---

## ASR finetuning experiments

We ran Automatic Speech Recognition experiments with a pre-completion subset of this dataset, you can find all the codes and configurations used for those experiments in the dedicated repository: [RobotsMali-AI/bambara-asr](https://github.com/RobotsMali-AI/bambara-asr/tree/main/afvoices). All the models can be found on [RobotsMali's HuggingFace profile](https://huggingface.co/RobotsMali/models)

---

## 4 · Prerequisites

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

## 5 · Mounting a Cloud Bucket

If you have copied that data on a GCS and want to test the pipeline, you can mount your bucket as follow:

1. Obtain **service‑account JSON credentials** with read‑write rights.
2. Run `setup.sh`:

   ```bash
   ./scripts/setup.sh <bucket> <cred.json> <assist_id> <mount_point> # (e.g mnt)
   ```

3. **Unmount** with `fusermount -u ./mnt` when done.

> **Tip** – make sure to unmount the bucket before shutting down your machine, just rerun `setup.sh` when you wish to recreate your work environment.

---

## 6 · License

Code is MIT‑licensed © 2025 RobotsMali AI4D Lab.  Audio are under Creative Common (cc-by-4.0).

## 7 · Citation

If you found this dataset useful for your research and wish to cite us, you can use this BibTex entry:

```bibtex
@misc{diarra2025dealinghardfactslowresource,
      title={Dealing with the Hard Facts of Low-Resource African NLP}, 
      author={Yacouba Diarra and Nouhoum Souleymane Coulibaly and Panga Azazia Kamaté and Madani Amadou Tall and Emmanuel Élisé Koné and Aymane Dembélé and Michael Leventhal},
      year={2025},
      eprint={2511.18557},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2511.18557}, 
}
```
