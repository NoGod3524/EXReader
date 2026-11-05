# Native iOS organization Toggle repair

Original343 organization tests failed5/6 on both mobile simulators. Earlier9019 fixedSize-only candidate also failed5/6. Retained original UI data proved the outer accessibility Switch included the label and empty horizontal space; even after shrinking, its center lay outside the actual native51x31 switch. A tap on that element therefore left value0 and the removed group unavailable.

This repair leaves the visible label in a separate HStack Text and gives the native Toggle a hidden visual label, explicit accessibility label and fixed intrinsic frame. The original identifier and onChange/model operation stay unchanged. The macOS Toggle stays byte-for-byte inside the original else branch. No hit-area workaround or changed tap helper is introduced in the frozen six tests.

The focused workflow rebuilds both same-source installed SDK/product targets and runs the original six organization cases, assertions and budgets on iPhone and iPad. Source admission permits only this exact iOS view substitution, the new admission/workflow/document; original tests, SDK core and product builder/checker remain343. No result is granted before actual Actions completion, and no fixed catalog update or full-product claim is made here.
