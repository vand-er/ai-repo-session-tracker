# The field guide rebuild: the map

Next for the owner, each in a fresh session (area 2 landed on `main`):

- **Build area 3, the shell**: its spec and tickets are `ready-for-agent`.

  ```text
  /implement-spec ~/code/field-guide/.scratch/rebuild-03-shell/spec.md
  ```

- **The map's next ticket**: [How search gets its records and settings](issues/21-search-gets-records.md), a
  grilling, area 5.

  ```text
  /wayfinder ~/code/field-guide/.scratch/field-guide-rebuild/map.md
  ```

Label: wayfinder:map

## Destination

Each of the 12 areas in [the grill's page](shared-understanding.md) has its open decisions made, and is ready for
the owner to run `/to-spec` and `/to-tickets` on it. The map itself writes no spec and no code.

## Notes

- **Start here.** Read [the grill's page](shared-understanding.md). Don't reopen what the page has settled.
- **Tickets** are `issues/NN-<slug>.md`, numbered in area order. Each has `Type:`, `Status:` (`open`, `claimed`,
  `resolved`), `Area:` and `Blocked by:` lines. The answer goes under `## Answer`, then `Status: resolved`, then one
  line here under *Decisions so far*.
- **Blocking.** `Blocked by:` lists direct blockers only. A research ticket waits on nothing.

## Decisions so far

<!-- one line per resolved ticket: [title](issues/NN-slug.md): gist -->

- [Where the style guide clashes with the app's own rules](issues/01-style-guide-clashes.md): The grill has already settled the style guide's direct clashes.
- [What the project rules keep, change and drop](issues/02-project-rules.md): Most rules stay.
- [The app's code conventions after the rebuild](issues/03-code-conventions.md): The app follows the style guide for layout and naming and lists only its own exceptions: long lines in data tables, and test names written as sentences.
- [What the contributor guide says after the rebuild](issues/04-contributor-guide.md): It keeps a short *Always* list, points at the style guide for code, and drops the paragraph on the old build script.
- [The glossary's new and retired words](issues/05-glossary.md): It adds Entry, Trip and Card, and retires Page and Sheet, which meant two things each.
- [Which test suites read which area](issues/06-test-suites.md): Nine suites.
- [How the sample trip's screens are pinned](issues/07-sample-trip-pin.md): A golden transcript of the sample trip, written once, regenerated only on the owner's word.
- [Which seams each area pins before it moves](issues/08-seams-per-area.md): Pins are coarse now and deep later.
- [Screens under a shell that never leaves, and a shared clock](issues/09-shell-and-clock.md): Swap screens on the next frame and load the new one in the background.
- [The shell's tree and what `open_screen` takes](issues/10-shell-and-open-screen.md): The shell holds one screen slot and an overlay layer.
- [What the app state holds](issues/11-app-state.md): The current trip, the open entry and the settings.
- [The app controller's events, calls and the clock](issues/12-app-controller.md): Four events and six calls, listed in the answer's table.
- [Where every file lands in the feature folders](issues/13-feature-folders.md): One folder per feature, each with its code, its records and its tests.
- [Records edited in a form and shipped in a build](issues/14-records-in-forms.md): A record edited in a form saves as text and ships as text.
- [Every authored file and the code that reads it](issues/15-authored-content.md): The entries folder has one reader and one writer.
- [A Species entry in the editor](issues/16-species-in-the-editor.md): Yes, in shape B: one record per Species, its fields grouped and each with a hint.
- [The other records' shapes](issues/17-other-records.md): Each follows the Species shape.
- [How records name each other and are found](issues/18-naming-and-finding.md): By a short id written in the record.
- [The move off the old CSV files](issues/19-off-csv.md): One script converts every file, and the old reader stays one release, behind a setting.
- [Every setting in search.py and who reads it](issues/20-settings.md): Forty settings.
- [Every piece the entry and map pages draw](issues/23-page-pieces.md): Fourteen pieces, all drawn by hand each frame.
- [Short sounds over a background track](issues/30-short-sounds.md): A pool of eight players covers the busiest screen, and the track runs on its own channel.
- [Every source of randomness in a quiz](issues/32-randomness.md): Every draw comes off the quiz's one seed, so a saved quiz needs the seed and its plain fields.
- [Hosting the photographers' shared folder](issues/34-photo-folder-hosting.md): Any of the three hosts compared fits.
- [Building a release from a clean commit](issues/37-release-from-clean-commit.md): A clean build needs the pinned toolchain and a fresh checkout.
- [Ask whether the photo licences allow a shared folder](issues/40-photo-licences.md): They do, for the app's own use.
- [The screenshot tool's log, list and tidying](issues/41-screenshot-log.md): It logs one line per shot, keeps a list of the last fifty, and tidies at start-up.
- [Does the map page survive a reload after every search?](issues/42-map-page-reload.md): Yes.

## Not yet specified

- **The menus, one by one** (area 8): each menu as a component, once the theme is decided.
- **The photos' move into feature folders** (area 11): waits on the species card's template.

## Out of scope

- **New features**: offline maps, a second language, and a field journal, all for afterwards.
- **Building any area**: the owner's `/to-spec`, `/to-tickets` and `/implement-spec`.
