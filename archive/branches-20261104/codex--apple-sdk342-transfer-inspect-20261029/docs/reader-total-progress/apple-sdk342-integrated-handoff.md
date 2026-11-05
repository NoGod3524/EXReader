# Apple SDK 3.42 integrated native gate

Source preparation follows 4a68d80fbaa524fc28f899d209d795248627080b. The new Actions driver compiles SDK 3.42 from the actual common source after comparing all frozen SDK paths to 8357eafa28423a7ab93ba08b823af80f01ad1505, installs legacy and raw wave3 product families, and records every installed file. The native wrapper authenticates both original same-run installations, invokes the unchanged Team24 runner with its 39 original cases and unchanged 240/360 second XCTest budgets, and checks the exact app source/SDK Info.plist plus dynamic library version and binary hashes.

The original owner guard executes on its original isolated approved owner candidate. The original shared binary checker, native runner, retained assertions, feature tests and original ZIP verifier are unchanged. The shared project generator only adds explicit 3.42 admission alongside 3.41 for existing page themes.

This first integrated source still carries the mobile picker candidate that failed on SDK 3.41; its independent repair is being handled separately. This branch establishes no passing gate, catalog increment, physical-device support or final joint delivery until its own Actions results and independent verification are complete. No default merge, PR, tag or release is performed.
