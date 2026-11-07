# Implementation notes

## Filter clocks

The One Euro filter estimates velocity from the difference between two sample
values divided by their elapsed time. If Windows returns the same clock value
for adjacent camera frames, that interval is zero; a decreasing timestamp is
also invalid for the derivative calculation. `main.py` timestamps each frame
with `time.perf_counter()`, a monotonic high-resolution clock suited to elapsed
time. Each hand owns separate pinch-midpoint and index-tip X/Y filters, and a
hand's filter state is discarded when it disappears. As a final guard,
`OneEuroFilter` ignores a sample whose timestamp is not newer than its previous
accepted sample and returns the previous filtered value.
