# docker build -t yolov9-onnx --build-arg MODEL_SIZE=t --build-arg IMG_SIZE=320 -o ../config/model_cache .

ARG MODEL_SIZE=c
ARG IMG_SIZE=640

FROM python:3.11-slim AS build

ARG MODEL_SIZE
ARG IMG_SIZE

RUN apt-get update && apt-get install -y --no-install-recommends \
    git libgl1 libglib2.0-0 cmake build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /yolov9

RUN git clone --depth 1 https://github.com/WongKinYiu/yolov9.git .

RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt onnx onnxsim onnxruntime onnxscript

ADD https://github.com/WongKinYiu/yolov9/releases/download/v0.1/yolov9-${MODEL_SIZE}-converted.pt yolov9-${MODEL_SIZE}.pt

RUN sed -i "s/ckpt = torch.load(attempt_download(w), map_location='cpu')/ckpt = torch.load(attempt_download(w), map_location='cpu', weights_only=False)/g" models/experimental.py

RUN python3 export.py --weights ./yolov9-${MODEL_SIZE}.pt --imgsz ${IMG_SIZE} --simplify --include onnx

RUN python3 -c "import onnx, ast; m = onnx.load('./yolov9-${MODEL_SIZE}.onnx'); props = {p.key: p.value for p in m.metadata_props}; names = ast.literal_eval(props.get('names', '{}')); f = open('./labelmap.txt', 'w'); f.write('\n'.join(names[k] for k in sorted(names.keys())) + '\n' if names else ''); f.close()"

FROM scratch

ARG MODEL_SIZE
ARG IMG_SIZE

COPY --from=build /yolov9/yolov9-${MODEL_SIZE}.onnx /yolov9-${MODEL_SIZE}-${IMG_SIZE}.onnx
COPY --from=build /yolov9/labelmap.txt /labelmap-${MODEL_SIZE}-${IMG_SIZE}.txt