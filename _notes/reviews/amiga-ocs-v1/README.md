# Amiga OCS Portrait v1 proof

The primary review artifact is
[`amiga-ocs-v1-pipeline-sheet.png`](amiga-ocs-v1-pipeline-sheet.png).
The final cards can be reviewed at full output size in
[`amiga-ocs-v1-card-set.png`](amiga-ocs-v1-card-set.png).

Each row shows the internal img2img-style master, the deterministic final art at
2× nearest-neighbour scale, and the complete pixel-native card. The first row
uses the stage-specific synthetic generation reference. The remaining rows use
six existing painterly outputs from `portrait-library/` to isolate the effect of
the deterministic renderer.

The proof fixes these properties across every portrait:

- 168×138 logical art, enlarged to 336×276 at exactly 2×
- one shared 32-colour palette on the Amiga OCS 12-bit RGB grid
- edge-aware 4×4 ordered dithering
- a complete 210×300 logical card enlarged to 420×600 at exactly 2×
- palette-limited pixel typography, borders, and art

The synthetic reference pair lives in
`tools/cards/assets/amiga-ocs-portrait-v1/`. The clean master is suitable for
the img2img generation stage. Its processed target exists for human review and
must not be sent back to the model.

Regenerate the local proof with:

```bash
uv run python -m tools.cards.amiga_proof \
  --output-dir _notes/reviews/amiga-ocs-v1 \
  --input 'Stage reference=tools/cards/assets/amiga-ocs-portrait-v1/generation-reference-01.png' \
  --input 'Evelyn Carvajal=portrait-library/runs/run_59c947b99f90/item_7d1e240db971.png' \
  --input 'Arian Fernandez=portrait-library/runs/run_59c947b99f90/item_c0857ddeced9.png' \
  --input 'Eduardo Lopez=portrait-library/runs/run_59c947b99f90/item_4715f4873061.png' \
  --input 'Yan Krukau=portrait-library/runs/run_59c947b99f90/item_2ae6affb60f7.png' \
  --input 'sudelermii=portrait-library/runs/run_59c947b99f90/item_cd41ba15804a.png' \
  --input 'John Eric Garcia=portrait-library/runs/run_59c947b99f90/item_1312499c9d9d.png'
```

This is an art-direction proof. It does not yet replace the six-stage UI or
the historical painterly/estate-pixel card treatments.
