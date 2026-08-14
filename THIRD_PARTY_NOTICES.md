# Third-Party Notices

This file records third-party source that appeared in the reachable Git
history of this repository. The paths described below are not present in the
current working tree and are not included in current `ai_tools` Python wheels.

## Historical source imports

Commit `3d7ee71` imported snapshots under `asc/mcp_agent_mail/` and
`asc/super-claude-kit/`. Commit `3dceb3e` subsequently removed those trees.
Their blobs remain available in Git history and retain the following notices.

### MCP Agent Mail

Upstream project: `Dicklesworthstone/mcp_agent_mail`

License in the imported snapshot: MIT

Copyright (c) 2025 Jeffrey Emanuel

### Super Claude Kit

Upstream project identified by the imported path and README:
`super-claude-kit`

The imported README declared the project to be licensed under the MIT License
and carried this notice:

Copyright (c) 2025 Arpit Nath

The snapshot did not contain the `LICENSE` file referenced by its README. This
notice preserves the declaration and copyright attribution without claiming
that the missing upstream file was present.

### MIT License text applicable to the notices above

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Design references that were not vendored

The current tree contains attributed design notes about OPCOM,
`dev-team-six`, and MCP Agent Mail, principally in
`docs/internal/LESSONS_FROM_OPCOM.md`. A 2026-08-14 comparison found no
nonempty exact-file match or normalized six-line block match between the
current `ai_tools` tree and the four reviewed `Toms_coder` repositories.
Those references are provenance for ideas and observations, not declarations
that third-party implementations are part of current `ai_tools` packages.
