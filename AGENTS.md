# Codex instructions

- The GitHub repository `pgrudzien12/openHornedRat` is public. Do not infer its visibility from older project notes; use `gh` to read current issues and pull requests.
- In Codex's default shell sandbox, `gh` may be unable to reach `api.github.com` even when the user is online and `gh` is authenticated. For GitHub read requests, use the shell tool's network-enabled `require_escalated` mode on the first attempt, with a narrow command prefix. Keep output compact with `--json` and `--jq`. A sandbox connection failure does not indicate a problem with the user's connection or login.
