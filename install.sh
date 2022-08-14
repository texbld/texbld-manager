#!/bin/sh

if command -V curl > /dev/null; then
curl -sSL https://raw.githubusercontent.com/texbld/texbld-manager/master/texbld-manager -o "/tmp/texbld-manager" || exit 1
else
  wget https://raw.githubusercontent.com/texbld/texbld-manager/master/texbld-manager -O "/tmp/texbld-manager" || exit 1
fi

python3 /tmp/texbld-manager setup
