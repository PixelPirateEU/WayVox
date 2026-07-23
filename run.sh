#!/usr/bin/env bash
# Script zum einfachen Starten von WayVox

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

if [ -d "venv" ]; then
    SITE_PACKAGES=$(venv/bin/python3 -c "import site; print(site.getsitepackages()[0])" 2>/dev/null)
    if [ -n "$SITE_PACKAGES" ]; then
        export LD_LIBRARY_PATH="$SITE_PACKAGES/nvidia/cublas/lib:$SITE_PACKAGES/nvidia/cudnn/lib:$SITE_PACKAGES/nvidia/cuda_runtime/lib:/opt/cuda/lib64:/opt/cuda/targets/x86_64-linux/lib:${LD_LIBRARY_PATH}"
    fi
    venv/bin/python3 main.py "$@"
else
    python3 main.py "$@"
fi
