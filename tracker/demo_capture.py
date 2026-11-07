"""Run the webcam capture demo."""

try:
    from .capture import main
except ImportError:  # Also allow: python tracker/demo_capture.py
    from capture import main


if __name__ == "__main__":
    main()
