# docker build -t yolo26s-onnx --build-arg MODEL_NAME=yolo26s-objv1-150 \
#   --build-arg IMG_SIZE=640 -o ../../config/model_cache -f Dockerfile .

ARG MODEL_NAME=yolo26s-objv1-150
ARG IMG_SIZE=640
# Optional: URL to fetch <MODEL_NAME>.pt from when it is not in weights/
ARG MODEL_URL=

FROM python:3.11-slim AS build

ARG MODEL_NAME
ARG IMG_SIZE
ARG MODEL_URL

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /export

# Install ultralytics and ONNX export dependencies
RUN pip install --no-cache-dir ultralytics onnx onnxscript onnxsim

# Checkpoint resolution: fetch from MODEL_URL when given, otherwise let
# Ultralytics resolve <MODEL_NAME>.pt by name. Weights are never committed —
# keep them out of the repo and pass a URL, or pre-place the .pt in the build
# context yourself.
RUN if [ -n "${MODEL_URL}" ]; then \
        echo "Downloading checkpoint: ${MODEL_URL}"; \
        curl -fsSL "${MODEL_URL}" -o "./${MODEL_NAME}.pt"; \
    else \
        echo "Resolving '${MODEL_NAME}.pt' via Ultralytics."; \
    fi

# Export model with end2end=False (Required for Frigate NMS post-processing)
RUN python3 -c "\
from ultralytics import YOLO; \
model = YOLO('${MODEL_NAME}.pt'); \
model.export(format='onnx', imgsz=${IMG_SIZE}, simplify=True, dynamic=False, end2end=False, half=True); \
open('labelmap.txt', 'w').write('\n'.join([model.names[i] for i in sorted(model.names.keys())]) + '\n') \
"

FROM scratch

ARG MODEL_NAME
ARG IMG_SIZE

COPY --from=build /export/${MODEL_NAME}.onnx /${MODEL_NAME}-${IMG_SIZE}-h.onnx
COPY --from=build /export/labelmap.txt /labelmap-${MODEL_NAME}-${IMG_SIZE}-h.txt
