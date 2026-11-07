# GestureCAD Blender receiver

The add-on targets Blender 4.x and listens on `127.0.0.1:8765` using a non-blocking UDP socket. Blender
application timers receive, queue, and apply messages on Blender's main thread.
Enabling the add-on starts the listener. In the 3D View sidebar, open the
**GestureCAD** tab to check the listener or stop/start it.

## Install

1. In Blender, open **Edit > Preferences > Add-ons** (called **Get Extensions**
   or **Extensions** in some Blender releases).
2. Choose **Install from Disk** and select
   `blender_addon/gesturecad_receiver.py` from this project.
3. Enable **GestureCAD UDP Receiver**. It starts listening at `127.0.0.1:8765`.
4. Keep the default `Cube` object in the scene, or send a `select` message for
   an existing object.

Run `python -m bridge.fake_sender` from the project root to send a scripted
camera-free test sequence. The sender defaults to `127.0.0.1:8765` and pauses
between actions. You can also send one JSON message with
`python -m bridge.sender '{"type":"translate","dx":0.01,"dy":0.0}'`.

Run `python main.py` from the project root to connect the webcam tracker,
voice input, and receiver. Add `--no-voice` to disable push-to-talk, or
`--dry-run` to print generated JSON messages without
sending UDP packets. Add `--calibrate` to draw the current camera calibration
rectangle; adjust it with `--calibration-rect LEFT TOP RIGHT BOTTOM`, using
normalized image coordinates from 0 to 1. For example:
`python main.py --calibrate --calibration-rect 0.15 0.1 0.85 0.9`.
The filtered index fingertip maps through this rectangle to normalized viewport
coordinates and sends cursor updates.

Install the voice dependencies with `pip install -r requirements.txt`.
Hold Space while the Webcam
preview is focused; release to transcribe and parse. The `tiny` model loads by
default; use `--stt-model base` for the larger model. The first run downloads
the selected model. Voice commands are printed and sent through the same UDP
bridge (or printed to the terminal in dry-run mode).

Each meaningful gesture, voice, cursor, and bridge event is appended with an
ISO timestamp to `gesturecad_events.jsonl`. Use `--log-file PATH` to choose a
different JSONL destination. Voice commands appear in the HUD for 1.5 seconds
before sending; say "cancel" to discard the pending command. `--no-confirm`
sends parsed voice commands immediately.

Hold an open palm for half a second to engage, then pinch to grab. A single
grabbed hand translates the active object in the view plane; two grabbed hands
scale and rotate it from their pinch-point spacing and angle. Changes in the
number or identity of grabbed hands re-clutch for one frame before motion
resumes. Translation sensitivity is `2.0` Blender units per normalized frame
unit, set in
`tracker/bridge_control.py`.

Supported messages:

```json
{"type":"translate","dx":0.01,"dy":0.0}
{"type":"scale","factor":1.1}
{"type":"rotate","axis":"z","radians":0.1}
{"type":"select","name":"Cube"}
{"type":"command","op":"move","axis":"z","value":0.05}
{"type":"command","op":"extrude","value":0.01}
{"type":"cursor","u":0.4,"v":0.6}
{"type":"undo"}
```

`translate` changes active-object X and Y location. `command` with `op: move`
changes one location axis. `scale` applies a uniform multiplier, and `rotate`
adds radians to the active object's Euler angle on the selected axis.
`command` with `op: extrude` extrudes the active mesh along Z in edit mode.
`cursor` draws a square in the 3D View and updates the add-on's
`pointer_world` scene value from a ray hit or the world ground plane. Grid
snapping is on by default at `0.01 m`; toggle it or change the spacing in the
GestureCAD sidebar.
