# Design and acceptance criteria

Audience: people sharing network performance evidence who can discard HTTP content.
Flow: load a local HAR, rebuild permitted fields, write a new HAR, inspect it, share deliberately.

The implementation has no HTTP client, telemetry, browser automation, configuration loading
or remote service. It builds every output object from scratch. It never recursively redacts
the input or forwards an unknown field. Numeric fields are finite and bounded; string fields
are constants, generated aliases, or exact members of short fixed allowlists. MIME parameters
are discarded. URL aliases are assigned by first appearance per origin and path; query, port,
credentials and fragment are absent in the output. No reversible alias map is written.

Dates are shifted by one common offset so the earliest page/request starts at 2000-01-01 UTC.
Capture spans above 366 days and naive/invalid timestamps are refused. Empty captures are valid.
Input is limited to 64 MiB and 100,000 entries/pages by default. JSON parsing uses memory
proportional to the input and rejects duplicate keys and non-finite values. The limits are
adjustable, so callers remain responsible for an appropriate process memory/CPU budget.

Acceptance criteria:

- Retain entry count, order, status, sizes, timing numbers, relative start times and endpoint correlation.
- Remove source host/path/query, HTTP contents, raw dates, page titles, IP/connection data and all extensions.
- Never overwrite an existing path, including the input and dangling symlinks.
- Fail before output creation on malformed structure or numeric values. Errors do not print capture values.
- Demonstrate an installed CLI flow, synthetic canaries, BOM, malformed JSON and input limits.

Non-goals: replay, content debugging, generic PII recognition, lossless transformation or
anonymity. Status/size/timing patterns remain observable and may be identifying. Numeric
fields can carry information. Two files do not receive globally stable pseudonyms. Custom
HTTP methods become OTHER and unknown MIME types become application/octet-stream.

HAR 1.2 is a historical de facto format. The abandoned W3C draft is background only; it is
not a current W3C Recommendation. Browser import compatibility must be tested in the target
browser; this version guarantees the documented JSON shape rather than every viewer.

All project code and synthetic fixtures were written for this project. No sanitizer source
or third-party asset was copied. Python's standard library is supplied by the user's Python
distribution. Setuptools is a build tool, Ruff is a development tool; neither is bundled.

Output creation checks the directory entry with lexists before opening exclusively, so
Windows dangling symlinks are refused. O_NOFOLLOW is also used where available, and POSIX
output permissions default to 0600. Use a destination directory you control; this is not a
security boundary against hostile concurrent replacement of filesystem entries.
