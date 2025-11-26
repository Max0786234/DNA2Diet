#!/bin/bash
echo "Using Python version:"
python3 --version

pip install --upgrade pip
pip install -r requirements.txt
git add .render-build.sh
git commit -m "Add render build script"
git push
