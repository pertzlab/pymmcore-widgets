# pertzlab integration branch

This branch is what pertzlab rigs install. It is a throwaway merge
product: never commit work here (except this file); rebuild it instead.

## Structure

- `main` (this fork and hinderling/pymmcore-widgets) mirrors
  `pymmcore-plus/pymmcore-widgets:main` and is never committed to.
- Development happens on branches of `hinderling/pymmcore-widgets`:
  - `feat/stage-map`: the StageMapWidget and the plate/position features
    it depends on (well-ID column, plate calibration, AffineState fix).
  - `patch/lab-tweaks`: lab-specific behavior and fixes not (yet)
    upstreamed (fov-size guard, PropertyWidget thread fix, autofocus
    restore, off-thread move-to-selection, per-position-only autofocus).
  - `fix/*`: one branch per open upstream PR
    (currently `fix/exposure-widget-thread-safety`, PR #563).

## Rebuild

```
git fetch upstream hinderling
git branch -f pertzlab <base>          # a commit on upstream main
git checkout pertzlab
git merge feat/stage-map patch/lab-tweaks fix/exposure-widget-thread-safety
# re-add this file if the base moved, then:
git push --force org pertzlab
git tag pertzlab-YYYY.MM.N && git push org pertzlab-YYYY.MM.N
```

Rebuild when: upstream `main` is synced to a new base, a branch above
gains commits, or an upstream PR merges (then delete its branch here).
Tag on every rig venv rebuild so runs are traceable to widget code.

Current base: d61a158 (upstream main as of 2026-08).
