# Portrait Workbench

Portrait Workbench is a browser-first, provenance-first portrait workflow:

**Sources → Explore → Finish → Build Set → Frames → Completed**

Explore is broad and disposable. Select 1–3 complete outputs from different
source portraits, iterate one generative Finish across that cohort, lock a
complete cohort, and build one named set from that immutable Finish. Painterly
and Estate Pixel are deterministic card Treatments in Frames, not Finish
choices.

## Start it

```bash
uv run python -m tools.portraits workbench-server
npm install
npm run dev
```

Open the Vite URL. The Python service creates an ignored `portrait-library/`
workspace, seeds two bundled estate style references, and creates a low-quality
live recipe. Set `PEXELS_API_KEY` for Pexels search and starter images. Set
`OPENROUTER_API_KEY` for live generation. Simulation is an explicit local
workflow fixture, not generated artwork.

## Browser workflow

1. **Sources:** search Pexels, upload images, inspect provenance, and choose an
   ordered project source set.
2. **Explore:** edit a recipe and generate immutable exploration runs. Select
   one complete output per source for the Finish handoff.
3. **Finish:** apply one plain-language finish change to the complete cohort.
   Trials are immutable and can be compared by candidate; only a complete trial
   can be locked.
4. **Build Set:** choose a locked Finish and name the set. Approved anchors are
   reused byte-for-byte; only remaining sources are generated.
5. **Frames:** drafts are created automatically for every ready active-set
   item. Choose Bust/Tall/Torso, then the deterministic Treatment Painterly or
   Estate Pixel.
6. **Completed:** keep cards from the active coherent set, download PNGs, or
   reconsider them in Frames. Historical sets and legacy cards remain
   accessible but are never mixed into the active grid.

The service validates missing keys, unavailable models, reference limits,
invalid counts, duplicate source candidates, checksum drift, incomplete
cohorts, and overlapping active runs. Exact returned usage and cost are
recorded on runs, locked Finishes, and sets. Set retries create a new
production run only for failed or interrupted items; successful items cannot
be rerun.

Finish inputs are generated artifacts, not new workspace sources. Set
production sends references in this exact order: current source identity,
approved locked-Finish anchors in candidate order, then the locked Finish's
original style references. Each run item records that mapping and its
checksums.

Missing run purposes read as `exploration`; cards without `set_id`,
`set_item_id`, and `finish_id` are legacy cards; missing `active_set_id` reads
as `null`. Existing runs, cards, and generated files are never destructively
migrated into a new set.

See [docs/portrait-workbench.md](docs/portrait-workbench.md) for the data
contracts, immutable provenance, preview caching, compatibility behavior, and
reset procedure.
