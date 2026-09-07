# pertzlab pymmcore-widgets fork

This repo collects the pymmcore-widgets improvements our microscopes use. It also keeps each improvement easy to send back to the original project (`pymmcore-plus/pymmcore-widgets`, called "upstream" below). This guide is for anyone in the lab who wants to change or add a widget. You do not need to know git well to follow it. Commands are given for every step.

## How it is organised

A branch is a separate copy of the code where one change is worked on, kept apart from everything else. This repo has three kinds:

- `main` is the untouched official version from upstream. Nobody edits it. Every new branch starts here.
- Feature branches each hold one improvement. For example, `feat/stage-map` holds the stage map widget and `feat/pfs-toggle-widget` holds the continuous-focus button. See "The branches today" for the full list.
- `pertzlab` is all the finished feature branches glued together. This is what the microscopes install and run. Nobody edits it by hand. When a feature branch changes, the maintainer throws `pertzlab` away and glues the branches together again. See "Rebuild".

On GitHub, the repo description and the default branch both point to `pertzlab`. Those are repo settings, not code, so a rebuild does not touch them.

## Set up your computer once

Clone this repo and add upstream as a second remote:

```
git clone https://github.com/pertzlab/pymmcore-widgets.git
cd pymmcore-widgets
git remote add upstream https://github.com/pymmcore-plus/pymmcore-widgets.git
git fetch --all
```

After cloning you are standing on `pertzlab`. Do not start work there. Switch to `main` first (the next section explains why):

```
git checkout main
```

If you cloned your own personal fork instead, add this repo as a remote and use that name wherever the commands below say `origin`.

## Where does my change go?

Two questions decide it.

**Question 1: Is it finished, tested, and something the microscopes should run?**

- Not yet, you are still experimenting, or only you need it: keep it on a branch that nobody else depends on. Work on it in this repo under your own name, for example `yourname/try-faster-snap`, or on a personal fork. Either way it affects nobody. Come back when it works. This is the normal starting point for all new work.
- Yes: it belongs in the shared collection. Go to question 2.

**Question 2: Would it help someone on a completely different microscope, not ours?**

- Yes, it is a clean general feature: give it its own `feat/...` branch, one feature per branch. `feat/stage-map` and `feat/pfs-toggle-widget` are examples. Later we can offer the branch to upstream as it is.
- It fixes a bug in upstream: make a `fix/...` branch, one per pull request. `fix/exposure-widget-thread-safety` is an example; it is open upstream as PR #563.
- No, it only makes sense for our lab, because it uses our device names, our specific setup, or changes behaviour in a way only we want: add it to `patch/lab-tweaks`, our shared lab-only branch. The fov-size guard and the per-position-only autofocus live there.

In short: experimental or only for you goes on your own branch. Proven and general goes on `feat/*`. Proven and fixing upstream goes on `fix/*`. Proven and lab-only goes on `patch/lab-tweaks`.

Two things to keep in mind:

- Keep one feature per `feat/*` branch. Small and focused is what makes it easy to review and to send upstream later. `patch/lab-tweaks` is the opposite on purpose. It is a pile of small lab-only tweaks that will never go upstream, so we keep them together on one branch.
- A lab-only tweak can move up later. If something in `patch/lab-tweaks` turns out to be useful for everyone, lift it onto its own `feat/*` branch, remove the lab-specific parts, and it becomes something we can offer upstream.

## Make a change, step by step

1. Start from a fresh `main`:

   ```
   git checkout main
   git pull upstream main
   ```

2. Create your branch. Pick the name using the section above:

   ```
   git checkout -b feat/my-new-widget
   ```

   To add to an existing shared branch instead, check it out and update it first:

   ```
   git checkout patch/lab-tweaks
   git pull origin patch/lab-tweaks
   ```

3. Make your change, then run the checks the project requires:

   ```
   uv run prek -a
   uv run pytest
   ```

4. Commit and push the branch to this repo:

   ```
   git add -A
   git commit -m "feat: add my new widget"
   git push -u origin feat/my-new-widget
   ```

5. If the branch is new and ready for the microscopes, add it to the merge list in the "Rebuild" section of this file and to "The branches today", then ask the maintainer to rebuild `pertzlab`. If you only added commits to a branch that is already in the list, just ask for a rebuild.

## Rules that keep this working

- Always start a new branch from `main`, never from `pertzlab`. A branch started from `pertzlab` quietly contains everyone else's changes too, and then you can never offer just your part to upstream.
- Keep each branch small and about one thing.
- Never edit `pertzlab` directly. Change the feature branch and rebuild.
- Push your branch to this repo before it goes into the rebuild. The rebuild merges what is on GitHub, not what is only on your computer.
- Do not commit to `main`. It must stay identical to upstream.

## Send a change upstream

When a `feat/*` or `fix/*` branch is proven and general, open a pull request from it against `pymmcore-plus/pymmcore-widgets:main`. This repo is a GitHub fork of upstream, so the pull request can be opened straight from here. Note the PR number next to the branch in "The branches today". Once the pull request merges upstream, sync `main` and remove the branch from the rebuild list; the change now arrives through `main`.

## The branches today

- `feat/stage-map`: the StageMapWidget and the plate and position features it depends on (well ID column, plate calibration, AffineState fix).
- `feat/pfs-toggle-widget`: ContinuousFocusWidget, a continuous-focus (PFS) button with a live status indicator and pluggable status sources.
- `patch/lab-tweaks`: lab-specific behaviour and fixes not yet upstreamed (fov-size guard, PropertyWidget thread fix, autofocus restore, off-thread move-to-selection, per-position-only autofocus).
- `fix/exposure-widget-thread-safety`: an upstream bug fix, open as PR #563.

## Rebuild

This section is for whoever maintains `pertzlab`.

One-time setup per clone, so you never resolve the same conflict twice:

```
git config rerere.enabled true
git config rerere.autoupdate true
```

The rebuild, run from anywhere in the clone:

```
git fetch --all
git branch -f pertzlab-prev pertzlab
git checkout -B pertzlab <base>
git checkout pertzlab-prev -- PERTZLAB.md .gitattributes
git commit -m "pertzlab: management files"
git branch -D pertzlab-prev
git merge --no-edit origin/feat/stage-map
git merge --no-edit origin/feat/pfs-toggle-widget
git merge --no-edit origin/patch/lab-tweaks
git merge --no-edit origin/fix/exposure-widget-thread-safety
git push --force origin pertzlab
git tag pertzlab-YYYY.MM.N
git push origin pertzlab-YYYY.MM.N
```

`<base>` is a commit on upstream `main`. The current one is listed at the bottom of this file.

What each step does:

- `pertzlab-prev` remembers where the old build was, so this file and `.gitattributes` can be copied onto the fresh base before merging. They must be in place before the merges, because git reads `.gitattributes` from the branch you merge into.
- The branches merge one at a time on purpose. If you merge them all in one command, git gives up at the first conflict and `rerere` cannot help. One at a time, a conflict stops only that merge: fix it, run `git commit`, and continue with the next line.
- The merges use `origin/...` so they pick up what is actually pushed to this repo.

Why rebuilding from scratch is not painful:

- `.gitattributes` marks the two `__init__.py` export files as `merge=union`. Union is a built-in git merge mode that keeps the lines from both sides instead of complaining. Every widget branch adds a line to these files, so this removes the most common conflict entirely. Sort the list by hand once if you want it alphabetical.
- `rerere` (enabled above) records how you fixed a real conflict the first time and applies the same fix by itself on every later rebuild.
- Rebase the feature branches onto the latest `main` now and then, instead of only merging them into `pertzlab`. This keeps them close to upstream, which means fewer conflicts and a clean pull request when the time comes.

Rebuild when upstream `main` moves to a new base, when a branch above gets new commits, or when an upstream pull request merges (then remove its branch from the list). Tag every build that a microscope installs, so a run can always be traced back to the exact widget code.

Current base: d61a158 (upstream main as of 2026-08).
