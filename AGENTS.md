Project: gesturecad, a webcam hand-gesture + voice controller for Blender.
The owner is a student whose main goal is LEARNING MediaPipe and OpenCV, not just getting working code.

Rules:
- Keep code simple and readable. No heavy abstractions or frameworks.
- Comment non-obvious lines, especially anything involving landmarks, coordinate systems, or thresholds.
- After each task, append a short section to docs/NOTES.md: what was built, the 3 key concepts used, and 2 things the owner should try changing to see what happens.
- Every task must end with a runnable demo and the exact command to run it.
- Pure logic (gesture math, voice parsing) lives in plain functions with pytest tests, separate from camera/Blender code.
- Layout: tracker/ (capture, hands, gestures, filters), voice/ (stt, parser), bridge/ (protocol, sender), blender_addon/, eval/, tests/, docs/.
- Python 3.11, a venv for the tracker. Blender add-on uses only Blender's bundled Python.
- Never use a feature you can't explain in NOTES.md.