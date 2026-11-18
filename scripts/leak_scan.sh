#!/bin/sh
# Scan commits for private terms before they reach the public remote.
#
# Usage: scripts/leak_scan.sh [<rev-range>]      (default: github/master..HEAD)
#
# Patterns live in a gitignored file (default: <repo>/.leak-terms), one
# case-insensitive POSIX extended regex per line; blank lines and lines
# starting with # are skipped. The list itself is private, so it must never be
# committed — that is why this script carries no terms of its own.
#
# Every commit in the range is scanned, not just the tip: a term added and
# later removed is still published history. For each commit this checks the
# message, every added line (binary files are read as text), the paths of
# changed and renamed files, and merge commits against their first parent.
#
# Not covered: author/committer identity (public by design in git), and any
# branch or tag outside the range you pass.
#
# Exit codes: 0 clean, 1 hits found, 2 cannot scan (fails closed).
set -eu

repo_root="$(git rev-parse --show-toplevel)"
terms_file="${LEAK_TERMS_FILE:-$repo_root/.leak-terms}"
range="${1:-github/master..HEAD}"

if [ ! -f "$terms_file" ]; then
  echo "leak-scan: no term list at $terms_file." >&2
  echo "leak-scan: create it (one regex per line) or set LEAK_TERMS_FILE; refusing to report clean without one." >&2
  exit 2
fi

if ! commits="$(git rev-list "$range" 2>/dev/null)"; then
  echo "leak-scan: cannot resolve '$range'; run 'git fetch github' or pass a valid rev-range." >&2
  exit 2
fi
commit_count="$(printf '%s' "$commits" | grep -c . || true)"

# Each commit is emitted as an unambiguous stream: a COMMIT line, the message
# with every line prefixed "MSG ", then the patch. Diff lines can never start
# with either marker, so message text that looks like a diff cannot hide.
emit_commits() {
  for commit in $commits; do
    printf 'COMMIT %s\n' "$(git rev-parse --short "$commit")"
    git log -1 --format=%B "$commit" | sed 's/^/MSG /'
    git show --text --no-color --diff-merges=first-parent --format= "$commit"
  done
}

# NUL bytes are dropped first: awk stops reading a line at the first NUL, which
# would hide everything after it in a binary file.
emit_commits | tr -d '\000' | awk -v terms="$terms_file" '
  BEGIN {
    while ((getline line < terms) > 0) {
      line_no++
      # A trailing space or CR (CRLF file) would otherwise make a term match nothing.
      sub(/[ \t\r]+$/, "", line)
      if (line ~ /^[[:space:]]*(#|$)/) continue
      pattern[line_no] = tolower(line)
      pattern_count++
    }
    if (pattern_count == 0) {
      print "leak-scan: " terms " has no patterns; refusing to report clean." > "/dev/stderr"
      unusable = 1
      exit 2
    }
  }
  function check(text, where,    lowered, i) {
    lowered = tolower(text)
    for (i in pattern) {
      if (lowered ~ pattern[i]) {
        hits[commit " " where " (term list line " i ")"]++
        total++
      }
    }
  }
  /^COMMIT /     { commit = $2; in_hunk = 0; next }
  /^MSG /        { check(substr($0, 5), "<commit message>"); next }
  /^diff --git / { in_hunk = 0; file = "<path>"; check(substr($0, 12), "<file path>"); next }
  # Inside a hunk every line is content; "+++ x" there is an added line "++ x".
  !in_hunk && /^(rename|copy) (from|to) / { check($0, "<file path>"); next }
  !in_hunk && /^\+\+\+ / { file = substr($0, 7); next }
  /^@@ /         { in_hunk = 1; next }
  in_hunk && /^\+/ { check(substr($0, 2), file) }
  END {
    if (unusable) exit 2
    for (key in hits) print "  " hits[key] " hit(s): " key
    exit (total > 0 ? 1 : 0)
  }
' && status=0 || status=$?

case "$status" in
  0) echo "leak-scan: clean ($commit_count commit(s) in $range)." ;;
  1) echo "leak-scan: private terms found in $range — rewrite those commits before pushing." >&2 ;;
esac
exit "$status"
