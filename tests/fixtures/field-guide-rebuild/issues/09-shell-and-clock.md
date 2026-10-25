# Screens under a shell that never leaves, and a shared clock

Type: research
Status: resolved
Area: 3, the shell
Blocked by: none
Findings: [research/shell-and-clock.md](../research/shell-and-clock.md), written when it resolves
Map: [The field guide rebuild: the map](../map.md)

## Question

Collect the facts on swapping a child screen under a shell that persists, and on one clock every screen reads.

## Pointers

- The grill's page, [shared-understanding.md](../shared-understanding.md), *Shape*.
- The research notes beside the map, [research-official-docs.md](../research-official-docs.md).

## Answer

Swap screens on the next frame and load the new one in the background. The clock reads the system time once per frame and hands the same value to every screen.
