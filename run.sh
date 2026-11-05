#!/bin/bash
# Roda um script do projeto no container, com o volume de trabalho. Uso: ./run.sh <script> [args]
SCRIPT=$1; shift
export MSYS_NO_PATHCONV=1
exec docker run --rm --name "emuflow-ppsspp-${SCRIPT%.sh}" \
  -v emuflow-ppsspp-work:/work \
  -v "D:\\WORKSPACE\\ppsspp-core:/src:ro" \
  -v "D:\\WORKSPACE\\ppsspp-core\\out:/out" \
  emuflow-ppsspp-build bash -c "tr -d '\r' < /src/$SCRIPT > /tmp/s.sh && bash /tmp/s.sh \"\$@\"" -- "$@"
