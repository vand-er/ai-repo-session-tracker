# The public repo starts from a fresh tree; the private history stays private

The board is published on GitHub as a new repo whose first commit is a scrubbed copy of the tree, tagged `v0.1.0`. The private repo it grew in, with its history, `.scratch/` Efforts and `docs/evidence/`, is never published. Those hold the owner's real boards, other projects and identity, and publishing can't be undone. We considered rewriting the private history to scrub it and then publishing that. We rejected it: a rewrite has to catch every personal string in every old commit, and one it misses undoes the scrub for good. The cost is that the public history starts at `v0.1.0`, and the decisions behind earlier code are known only from the ADRs and the code itself.

## Consequences

- After the release, the public repo is the home: new Efforts and evidence are written there, in public, so they must be written with that in mind.
- A personal-strings check guards every public commit. Its generic patterns live in the repo. The owner's own names live outside it, because a public list of them would itself give the owner away.
