#!/usr/bin/env bash
# Verifica che PKGBUILD (root, build locale) e aur/PKGBUILD (pubblicato dal
# workflow di release) restino allineati sulle dipendenze. I due file sono
# distinti perché differiscono su source/build, ma depends/makedepends/optdepends
# devono coincidere: una divergenza silenziosa qui ha già spedito un pacchetto
# AUR senza python-cairo.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

# Estrae le array di dipendenze da un PKGBUILD, ordinate e normalizzate.
# Il source avviene in subshell: definisce le variabili senza eseguire build()/package().
extract_deps() {
    (
        set +u
        # shellcheck disable=SC1090
        source "$1"
        printf 'depends: %s\n'     "$(printf '%s\n' "${depends[@]}"     | sort | paste -sd,)"
        printf 'makedepends: %s\n' "$(printf '%s\n' "${makedepends[@]}" | sort | paste -sd,)"
        printf 'optdepends: %s\n'  "$(printf '%s\n' "${optdepends[@]}"  | sort | paste -sd,)"
    )
}

if diff -u \
    <(extract_deps "$ROOT/PKGBUILD") \
    <(extract_deps "$ROOT/aur/PKGBUILD"); then
    echo "OK: dipendenze allineate tra PKGBUILD e aur/PKGBUILD"
else
    echo "ERRORE: PKGBUILD e aur/PKGBUILD divergono sulle dipendenze (vedi diff sopra)." >&2
    exit 1
fi
