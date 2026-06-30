# PDF Number Editor

A small local drag-and-drop app for replacing PDF numbers using a two-column mapping file.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

Open the URL shown in the terminal, usually:

```text
http://127.0.0.1:8765
```

## Use

1. Drop the source PDF files onto the page.
2. Drop a `.csv` or `.tsv` mapping file, or paste mapping rows into the mapping box.
3. Click **Process PDFs**.
4. Download the ZIP of edited PDFs.

The mapping file uses two columns:

```csv
old_number,new_number
12345,67890
```

Each source PDF should be named after the old number, for example `12345.pdf`.

## Build a Standalone Windows EXE

Build this on a Windows computer:

1. Install Python from <https://www.python.org/downloads/windows/> and tick **Add python.exe to PATH**.
2. Copy this whole folder to the Windows computer.
3. Double-click `build_windows.bat`.
4. Send users the generated file: `dist\PDF Number Editor.exe`.

Users do not need Python, PyMuPDF, pip, or this source folder. They only double-click the EXE.

The app runs locally on the user's computer and opens the browser automatically. PDFs are not uploaded online. Windows may show a SmartScreen warning because the EXE is not code-signed.
