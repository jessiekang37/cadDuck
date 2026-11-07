"""Download the MediaPipe Hand Landmarker model into this tracker directory."""

from pathlib import Path
from urllib.request import urlretrieve


MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
MODEL_PATH = Path(__file__).with_name("hand_landmarker.task")


def main() -> None:
    """Download ``hand_landmarker.task`` next to this script."""
    print(f"Downloading Hand Landmarker model to {MODEL_PATH}")
    urlretrieve(MODEL_URL, MODEL_PATH)
    print("Download complete.")


if __name__ == "__main__":
    main()
