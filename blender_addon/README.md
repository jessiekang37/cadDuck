# GestureCAD Blender receiver

The add-on listens on `127.0.0.1:8765` using a non-blocking UDP socket. Blender
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

Supported messages:

```json
{"type":"translate","dx":0.01,"dy":0.0}
{"type":"scale","factor":1.1}
{"type":"rotate","axis":"z","radians":0.1}
{"type":"select","name":"Cube"}
{"type":"command","op":"move","axis":"z","value":0.05}
{"type":"undo"}
```

`translate` changes active-object X and Y location. `command` with `op: move`
changes one location axis. `scale` applies a uniform multiplier, and `rotate`
adds radians to the active object's Euler angle on the selected axis.
