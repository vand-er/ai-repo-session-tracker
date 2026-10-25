# Domain docs

This repo has one context: one `GLOSSARY.md` and one `docs/adr/`, both at the repo root.

## Before exploring, read these

- **`GLOSSARY.md`**: the Board's words (Board, Effort, Ticket, Mark, Landed, ...) and the synonyms each one avoids.
- **`docs/adr/`**: the ADRs that touch the area you're about to work in.

## Use the glossary's vocabulary

When your output names a domain concept (in a Ticket title, a refactor proposal, a hypothesis, a test name), use the term as `GLOSSARY.md` defines it, never a synonym it lists under *Avoid*.

If the concept you need isn't in the glossary yet, either you're inventing language the project doesn't use (reconsider), or there's a real gap. Once the term is settled, add it to `GLOSSARY.md` in the same shape as its neighbours: the term in bold, a one-line definition, then *Avoid*. Keep the file a glossary only. (`/domain-modeling` from Matt Pocock's skills, <https://github.com/mattpocock/skills>, does this for you if you have it.)

## Record hard-to-reverse decisions

A decision that is hard to reverse, surprising without its reason, and a real trade-off gets an ADR: `docs/adr/NNNN-<slug>.md`, the next number, shaped like the ones there (the decision and why in a paragraph, then *Consequences*).

## Flag ADR conflicts

If your output contradicts an existing ADR, say so explicitly rather than silently overriding it:

> _Contradicts ADR 0002 (Builders read from Claude Code files), but worth reopening because…_
