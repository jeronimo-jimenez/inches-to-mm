# Program to upload a plane and convert its measures in inches to mm

## Installation guide

1. Open a CMD session in any folder and do ```git clone https://github.com/jeronimo-jimenez/inches-to-mm.git```
2. Navigate to src folder and install requirements
      ```python
      pip install -r requirements.txt
      ```
3. Install tesseract only if you want to use the tesseract-based script.
4. Execute your chosen script.

## Scripts

- **inches_to_mm_tesseract.py**: uses Tesseract to extract the text.
- **inches_to_mm.py**: uses PaddleOCR. Works worse than Tesseract.
