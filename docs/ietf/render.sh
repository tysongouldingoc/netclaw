#!/usr/bin/env bash
# Render the NCFED Internet-Draft: kramdown-rfc markdown -> RFCXML v3 + text.
#
# Output (canonical, committed):
#   rendered/${DRAFT}.xml   — RFCXML v3, the Datatracker submission file
#   rendered/${DRAFT}.txt   — text render of the same content
#
# kdrfc's v2 intermediates land next to the source; they are removed after a
# successful render so the only draft files in this directory stay the .md.
set -euo pipefail
cd "$(dirname "$0")"

DRAFT="draft-capobianco-ncfed-02"

# The apt ruby3.0 that /usr/local/bin/kdrfc's shebang points at was removed by
# the 26.04 upgrade; the working gem lives in the user install for ruby3.3.
GEM_BIN="$HOME/.local/share/gem/ruby/3.3.0/bin"
[ -x "$GEM_BIN/kdrfc" ] && export PATH="$GEM_BIN:$PATH"
command -v kdrfc >/dev/null || { echo "kdrfc not found — gem install --user-install kramdown-rfc" >&2; exit 1; }
command -v xml2rfc >/dev/null || { echo "xml2rfc not found — pip install xml2rfc" >&2; exit 1; }

kdrfc "${DRAFT}.md"
xml2rfc --v2v3 "${DRAFT}.xml" -o "rendered/${DRAFT}.xml"
xml2rfc "rendered/${DRAFT}.xml" --text -o "rendered/${DRAFT}.txt"
rm -f "${DRAFT}.xml" "${DRAFT}.txt"

echo ""
echo "Rendered: rendered/${DRAFT}.xml (submit this) + rendered/${DRAFT}.txt"
