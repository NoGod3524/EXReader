# L05 console acceptance

Build on Windows with the installed reading SDK used by the reference host:

```powershell
cmake -S examples/windows/find_acceptance -B build/l05-find -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_SDK=<SDK-prefix>
cmake --build build/l05-find --target check_shell_docedit_find -j 3
ctest --test-dir build/l05-find --output-on-failure -V
```

The target compiles the current tree's engine model, and
includes the real host selection/input code. It creates no windows and sends no
input. Checks cover selection navigation, replacement, one-step undo/redo,
overlaps, cross-run formatting, rollback, Chinese and emoji.

`host-integration.patch` contains the shared-file hooks, left unapplied because
L05's exclusive scope does not authorize changes to those files. Check it with
`git apply --check examples/windows/find_acceptance/host-integration.patch`.
After integration, verify the bar, keyboard focus and scrolling in the host.
