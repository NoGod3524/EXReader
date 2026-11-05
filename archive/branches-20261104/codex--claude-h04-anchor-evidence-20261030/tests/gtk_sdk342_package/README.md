# GTK SDK 3.42 and same-source Linux package

Actions-only opt-in from d1e6bd072a904150bb292994d0cf7d95ccde5c19.
SDK 3.42 origin is 7271829a829bfa6aaa47b73077c493f71af27ad3; this package
never changes SDK source, public headers, default SDK version, migration or old tests.

The host enables exactly 3.41.0 or 3.42.0 for GTK raw3/Wave3. The default remains
3.40.0, all find_package calls remain EXACT, raw/legacy prefix guards remain intact.
The standalone Linux packaging CLI now admits explicit 3.42.0 with the same ABI
and dependency verification. New producer adapter supplies 3.42.0 only at command
boundaries of unchanged raw/legacy producers and original F06 packaging tools.

The workflow retains raw/legacy installed-family checks, native Wave3 backend,
real GTK navigation and folder-import backends, owner-fault tests and both GUI
suites, then authenticates original artifacts, package and actual host identity.
Full historical G13/five-tools GUI and unrelated GTK suites are not claimed.
The Linux archive is an unsigned GTK3 portable development package, not deb/rpm,
not a signed release, and does not grant other-platform acceptance.

For six-platform composition, cherry-pick the host/packager changes; explicitly
supply SDK 3.42.0 to the Linux producer and S20 assemble/verify commands. Preserve
the original F06 defaults for other platforms. Run the resulting common source;
this branch's evidence is not reusable for a changed SHA.

## Preserved initial failure

Run 40649465218, SHA 85972e38165749768d8064a85ff46e6ba8cf16bf:
SDK/GTK build, raw 20-check backend, legacy link, real SDK3.42 identity and
archive/unpack passed before the new cache audit incorrectly demanded CMake
STRING type for otherwise valid UNINITIALIZED version variables in SDK-free
modules. Corrected to compare exact version value, not incidental cache type.
Authentication's urllib redirect also forwarded GitHub Authorization to blob
storage; use the established gh API download path. Neither fix changes product
assertions. Original failure artifact 12799650451 remains retained.
