# macOS annotation disclosure correction

The original same-source three-platform run 40911433448 at d5327faa540d2e19978e5b76e387f99457a60936 remains failed on macOS. Original artifact 12916537324 was authenticated and read in Actions 40918194712 and 40918573780. The test tapped the centre of the native disclosure control, whose value remained 0; the JSONL export control remained unavailable.

This independent macOS candidate taps the native triangle at its leading edge and requires the export control to become present. It preserves all original behavioral assertions, budgets and five native suite phases. It is scoped to macOS only; it cannot turn the older three-platform run green or claim a combined-source Apple pass. iPhone/iPad originals are still running on their original source.
