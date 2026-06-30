#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "Installing build tools on this Mac..."
python3 -m pip install -r requirements.txt pyinstaller

echo "Building standalone macOS app..."
python3 -m PyInstaller \
  --clean \
  --noconfirm \
  --onefile \
  --windowed \
  --name "PDF Number Editor" \
  app.py

echo ""
echo "Done."
echo "Mac app is here:"
echo "$PWD/dist/PDF Number Editor"
echo ""
echo "For Windows, build on a Windows computer using build_windows.bat."
