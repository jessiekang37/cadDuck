# GestureCAD task evaluation

Run one participant condition per Blender UI session. From the project root:

```text
blender --python eval/run_eval.py -- --participant P001 --condition gesture+voice
blender --python eval/run_eval.py -- --participant P001 --condition mouse+keyboard
```

The runner creates a separate evaluation scene and opens an **Evaluation** tab
in the 3D View sidebar. Start each task when the participant begins, use
**Mark Error** for each observed error (optionally enter a note), and end the
task when it is complete. Tasks must be completed in order.

1. Orbit to azimuth 45 degrees and elevation 30 degrees, then place
   `Eval_Cube` on the red ring.
2. Set `Eval_Box` dimensions to **1.20 x 0.80 x 1.50 m**. The same values are
   shown on a dimension card in the scene and in the Evaluation panel.
3. Rotate, scale, and place `Eval_Cube_B`, `Eval_Sphere`, and `Eval_Cone` to
   match [reference.svg](reference.svg).

After all three tasks, enter the six raw NASA-TLX ratings with the 0-20 sliders
and save the condition. Performance is oriented so 0 means best and 20 means
worst. The CSV stores one row per participant-condition, including UTC task
start/end timestamps, elapsed seconds, error counts, and all six ratings.

By default, condition rows append to `eval/results.csv` and timestamped task
events append to `eval/events.jsonl`. Override either path with `--csv PATH`
or `--events PATH`. Summarize condition means with:

```text
python eval/summarize.py
python eval/summarize.py eval/results.csv --output eval/summary.csv
```

Each Blender process records one condition. Restart Blender before launching
the other condition for the same participant.
