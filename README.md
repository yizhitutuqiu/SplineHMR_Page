# SplineHMR Project Page

Static project homepage for **SplineHMR: A Universal B-spline Prior for Temporally Stable SMPL Refinement**.

Open `index.html` locally, or serve this directory with GitHub Pages.

## Presentation media

The temporal-coupling diagrams come from slides 3–4 of the authors' final ACM
Multimedia 2026 presentation. The robustness section combines all four embedded
clips from slide 12 (clean/noisy guidance) and slide 13 (unmasked/masked guidance)
into one synchronized MP4 per slide. Each MP4 is 8 seconds, 30 fps, H.264/yuv420p,
1600×900, and strictly smaller than 5,000,000 bytes, with fast-start metadata.
The native four-method layouts and red/green overlays are preserved.

Prebuilt images and videos are self-contained in `assets/`; hosting requires no
PPTX, Python packages, inference environment, or build step. Source-member hashes
and output validation are recorded in `assets/presentation_media.json`.

To regenerate the media from an authorized copy of the presentation (optional;
requires Pillow, numpy, OpenCV, PyAV, a C compiler, and libpng development headers):

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  nice -n 19 python tools/build_presentation_assets.py --pptx /path/to/SplineHMR_ACMMM2026_Final.pptx
```

The exporter is serial and single-threaded and uses no GPU. Its libpng helper
reads the large source PNG one row at a time and area-averages blocks before
compositing, rather than allocating a full-resolution image in memory.

Run `python tools/check_site.py` for inexpensive static-link, accessibility,
media-hash, timeline-metadata, and file-size checks. The exporter additionally
decodes every output frame and checks MP4 fast-start atom ordering.
