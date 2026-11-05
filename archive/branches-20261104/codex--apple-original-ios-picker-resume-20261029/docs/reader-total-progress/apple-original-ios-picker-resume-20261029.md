# iOS original save picker continuation

The earlier run [40647623322](https://github.com/NoGod3524/EXReader/actions/runs/40647623322) failed on both iOS simulators. Its iPhone failure hierarchy showed the Files inline rename editor still focused with the intended folder name when the test could not activate Open. This candidate attempts to commit the rename by tapping the picker navigation area, asserts that the editor closes, and retains the original native picker and byte-for-byte readback assertions. It does not establish that the change works until its exact Actions run succeeds. The old failure remains.

Only iPhone and iPad are run here; SDK 3.41 remains the original test scope. Physical devices, SDK 3.42 and common-source product acceptance are separate.
