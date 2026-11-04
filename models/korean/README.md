# 한국어 인식 모델

`rec.onnx`, `dict.txt` 는 PaddleOCR 의 한국어 텍스트 인식 모델을 ONNX 로 변환한 것입니다.

- 원본: https://huggingface.co/monkt/paddleocr-onnx (`languages/korean/`)
- 라이선스: Apache-2.0 (PaddleOCR)

이 파일들이 있으면 RapidOCR 백엔드가 한국어와 영어를 함께 인식합니다.
없으면 기본(중국어+영어) 모델로 동작하며 한글은 인식되지 않습니다.

다시 받으려면 프로젝트 폴더에서:

```bat
.venv\Scripts\python.exe tools\fetch_models.py
```
