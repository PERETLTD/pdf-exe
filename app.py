#!/usr/bin/env python3
import csv
from email.parser import BytesParser
from email import policy
import html
import io
import json
import os
import shutil
import sys
import tempfile
import time
import threading
import traceback
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


APP_HOST = "127.0.0.1"
DEFAULT_APP_PORT = int(os.environ.get("PDF_EDITOR_PORT", "8765"))
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024

REPLACEMENT_FONT_SIZE = 13.68
FONT_NAME = "helv"
VISUAL_MOVE_RIGHT_POINTS = 0
VISUAL_MOVE_DOWN_POINTS = 10

REDACT_PAD_LEFT = 0
REDACT_PAD_TOP = 0
REDACT_PAD_RIGHT = 0
REDACT_PAD_BOTTOM = 0

RUNS = {}


def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def log_path():
    return app_dir() / "PDF Number Editor.log"


def log_error(message):
    try:
        with log_path().open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
            f.write(traceback.format_exc())
            f.write("\n")
    except Exception:
        pass


def log_info(message):
    try:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
        if sys.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
        with log_path().open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


class UploadedFile:
    def __init__(self, filename, data):
        self.filename = filename
        self.file = io.BytesIO(data)


def parse_multipart_form(headers, body):
    content_type = headers.get("Content-Type", "")
    message_bytes = (
        f"Content-Type: {content_type}\r\n"
        "MIME-Version: 1.0\r\n"
        "\r\n"
    ).encode("utf-8") + body

    message = BytesParser(policy=policy.default).parsebytes(message_bytes)
    if not message.is_multipart():
        raise ValueError("Expected multipart form upload.")

    mapping_text = ""
    pdf_fields = []

    for part in message.iter_parts():
        disposition = part.get("Content-Disposition", "")
        if "form-data" not in disposition:
            continue

        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""

        if name == "mapping":
            charset = part.get_content_charset() or "utf-8"
            mapping_text = payload.decode(charset, errors="replace")
        elif name == "pdfs" and filename:
            pdf_fields.append(UploadedFile(filename, payload))

    return mapping_text, pdf_fields


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PDF Number Editor</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17202a;
      --muted: #5d6b7a;
      --line: #c9d4df;
      --panel: #ffffff;
      --bg: #f4f7fa;
      --accent: #007a6e;
      --accent-strong: #005f56;
      --danger: #b3261e;
      --ok: #166534;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }

    main {
      width: min(1120px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }

    header {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: flex-end;
      margin-bottom: 18px;
    }

    h1 {
      margin: 0;
      font-size: clamp(28px, 4vw, 42px);
      line-height: 1.05;
      letter-spacing: 0;
    }

    .subtitle {
      margin: 10px 0 0;
      color: var(--muted);
      max-width: 680px;
      line-height: 1.5;
      font-size: 15px;
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
      gap: 16px;
      align-items: start;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 12px 30px rgba(30, 48, 70, 0.07);
    }

    .dropzone {
      min-height: 260px;
      display: grid;
      place-items: center;
      text-align: center;
      border: 2px dashed #8ea4b7;
      border-radius: 8px;
      background: #fbfdff;
      padding: 24px;
      transition: border-color 120ms ease, background 120ms ease, transform 120ms ease;
    }

    .dropzone.dragging {
      border-color: var(--accent);
      background: #eefaf8;
      transform: translateY(-1px);
    }

    .drop-title {
      margin: 0;
      font-size: 20px;
      font-weight: 750;
    }

    .drop-copy {
      margin: 8px auto 0;
      color: var(--muted);
      max-width: 520px;
      line-height: 1.45;
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }

    button, .file-button, .download {
      min-height: 40px;
      border: 1px solid transparent;
      border-radius: 7px;
      padding: 0 14px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      font: inherit;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
    }

    button.primary {
      color: white;
      background: var(--accent);
    }

    button.primary:hover { background: var(--accent-strong); }

    button.secondary, .file-button {
      color: var(--ink);
      background: #eef3f7;
      border-color: #d3dee8;
    }

    button:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }

    input[type="file"] {
      position: absolute;
      width: 1px;
      height: 1px;
      opacity: 0;
      pointer-events: none;
    }

    .section-title {
      margin: 0 0 10px;
      font-size: 15px;
      font-weight: 800;
      color: #263442;
    }

    .file-list {
      display: grid;
      gap: 8px;
      margin-top: 12px;
      max-height: 260px;
      overflow: auto;
      padding-right: 2px;
    }

    .file-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      min-height: 42px;
      border: 1px solid #d9e2ea;
      background: #fbfcfe;
      border-radius: 7px;
      padding: 8px 10px;
    }

    .file-name {
      overflow-wrap: anywhere;
      font-size: 14px;
      font-weight: 650;
    }

    .file-meta {
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }

    .mapping {
      display: grid;
      gap: 10px;
    }

    .mapping-box {
      width: 100%;
      min-height: 180px;
      resize: vertical;
      border: 1px solid #cdd8e2;
      border-radius: 7px;
      padding: 10px;
      font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      color: var(--ink);
      background: #fbfcfe;
    }

    .hint {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
      margin: 0;
    }

    .status {
      margin-top: 14px;
      border: 1px solid #cdd8e2;
      background: #fbfcfe;
      border-radius: 8px;
      min-height: 150px;
      padding: 12px;
      overflow: auto;
      font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre-wrap;
    }

    .download {
      background: #1f5f99;
      color: white;
    }

    .ok { color: var(--ok); }
    .error { color: var(--danger); }

    @media (max-width: 820px) {
      main { width: min(100vw - 20px, 680px); padding-top: 18px; }
      header { display: block; }
      .layout { grid-template-columns: 1fr; }
      .dropzone { min-height: 220px; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>PDF Number Editor</h1>
        <p class="subtitle">Drop the source PDFs and provide the old-to-new number mapping. The app edits every matching PDF and returns a ZIP of the finished files.</p>
      </div>
    </header>

    <div class="layout">
      <section class="panel">
        <div id="dropzone" class="dropzone">
          <div>
            <p class="drop-title">Drop PDFs and a mapping CSV here</p>
            <p class="drop-copy">You can also pick files manually. The mapping file should have two columns: old number, new number.</p>
            <div class="actions">
              <label class="file-button" for="fileInput">Choose files</label>
              <button id="clearFiles" class="secondary" type="button">Clear</button>
            </div>
          </div>
        </div>
        <input id="fileInput" type="file" multiple accept=".pdf,.csv,.tsv,text/csv,text/tab-separated-values">
        <div class="file-list" id="fileList"></div>
      </section>

      <aside class="panel mapping">
        <div>
          <p class="section-title">Mapping</p>
          <p class="hint">Drop a CSV/TSV, or paste rows below. Example: <strong>12345,67890</strong></p>
        </div>
        <textarea id="mappingText" class="mapping-box" spellcheck="false" placeholder="old_number,new_number&#10;12345,67890"></textarea>
        <div class="actions">
          <button id="process" class="primary" type="button">Process PDFs</button>
          <a id="download" class="download" href="#" hidden>Download ZIP</a>
        </div>
        <div id="status" class="status">Ready.</div>
      </aside>
    </div>
  </main>

  <script>
    const files = new Map();
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("fileInput");
    const fileList = document.getElementById("fileList");
    const mappingText = document.getElementById("mappingText");
    const statusBox = document.getElementById("status");
    const processButton = document.getElementById("process");
    const downloadLink = document.getElementById("download");
    const clearFiles = document.getElementById("clearFiles");

    function keyFor(file) {
      return `${file.name}:${file.size}:${file.lastModified}`;
    }

    function formatBytes(bytes) {
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    }

    async function addFiles(selected) {
      for (const file of selected) {
        const lower = file.name.toLowerCase();
        if (lower.endsWith(".csv") || lower.endsWith(".tsv")) {
          mappingText.value = await file.text();
        } else if (lower.endsWith(".pdf")) {
          files.set(keyFor(file), file);
        }
      }
      renderFiles();
    }

    function renderFiles() {
      fileList.innerHTML = "";
      for (const [key, file] of files.entries()) {
        const row = document.createElement("div");
        row.className = "file-row";
        row.innerHTML = `<div class="file-name"></div><div class="file-meta">${formatBytes(file.size)}</div>`;
        row.querySelector(".file-name").textContent = file.name;
        row.addEventListener("dblclick", () => {
          files.delete(key);
          renderFiles();
        });
        fileList.appendChild(row);
      }
      if (!files.size) {
        fileList.innerHTML = '<p class="hint">No PDFs selected yet.</p>';
      }
    }

    function setStatus(text, className = "") {
      statusBox.className = `status ${className}`;
      statusBox.textContent = text;
    }

    ["dragenter", "dragover"].forEach(eventName => {
      dropzone.addEventListener(eventName, event => {
        event.preventDefault();
        dropzone.classList.add("dragging");
      });
    });

    ["dragleave", "drop"].forEach(eventName => {
      dropzone.addEventListener(eventName, event => {
        event.preventDefault();
        dropzone.classList.remove("dragging");
      });
    });

    dropzone.addEventListener("drop", event => addFiles(event.dataTransfer.files));
    fileInput.addEventListener("change", event => addFiles(event.target.files));

    clearFiles.addEventListener("click", () => {
      files.clear();
      fileInput.value = "";
      downloadLink.hidden = true;
      renderFiles();
      setStatus("Ready.");
    });

    processButton.addEventListener("click", async () => {
      downloadLink.hidden = true;

      if (!files.size) {
        setStatus("Add at least one PDF.", "error");
        return;
      }
      if (!mappingText.value.trim()) {
        setStatus("Add a mapping CSV or paste mapping rows.", "error");
        return;
      }

      const form = new FormData();
      for (const file of files.values()) form.append("pdfs", file, file.name);
      form.append("mapping", mappingText.value);

      processButton.disabled = true;
      setStatus("Processing...");

      try {
        const response = await fetch("/process", { method: "POST", body: form });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Processing failed.");

        setStatus(result.log.join("\n"), result.created > 0 ? "ok" : "");
        downloadLink.href = `/download?id=${encodeURIComponent(result.id)}`;
        downloadLink.hidden = result.created === 0;
      } catch (error) {
        setStatus(error.message, "error");
      } finally {
        processButton.disabled = false;
      }
    });

    renderFiles();
  </script>
</body>
</html>
"""


def safe_filename(name):
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "-")
    return name.strip() or "edited"


def parse_mapping(text):
    sample = text[:4096]
    delimiter = "\t" if "\t" in sample else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = []

    for row in reader:
        if len(row) < 2:
            continue

        old_number = row[0].strip()
        new_number = row[1].strip()

        if not old_number or not new_number:
            continue

        if old_number.lower() in {
            "originalnumber",
            "original number",
            "original_number",
            "old number",
            "old_number",
            "source",
            "column a",
        }:
            continue

        rows.append((old_number, new_number))

    return rows


def pick_one_position(replacements):
    replacements = sorted(
        replacements,
        key=lambda item: (item[0], item[1].y0, item[1].x0),
    )
    max_y = max(area.y0 for _, area in replacements)
    bottom_matches = [
        (page_index, area)
        for page_index, area in replacements
        if abs(area.y0 - max_y) < 5
    ]
    return sorted(bottom_matches, key=lambda item: item[1].x0)[0]


def apply_visual_offset(page, point, move_right, move_down):
    rotation = page.rotation % 360

    if rotation == 0:
        return fitz.Point(point.x + move_right, point.y + move_down)
    if rotation == 90:
        return fitz.Point(point.x + move_down, point.y - move_right)
    if rotation == 180:
        return fitz.Point(point.x - move_right, point.y - move_down)
    if rotation == 270:
        return fitz.Point(point.x - move_down, point.y + move_right)

    return fitz.Point(point.x + move_right, point.y + move_down)


def unique_output_path(folder, filename):
    path = folder / filename
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = folder / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def process_pdfs(uploaded_files, mapping_text):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. Run: python3 -m pip install -r requirements.txt")

    rows = parse_mapping(mapping_text)
    if not rows:
        raise ValueError("No valid mapping rows found.")

    run_id = uuid.uuid4().hex
    run_dir = Path(tempfile.mkdtemp(prefix=f"pdf-editor-{run_id}-"))
    source_dir = run_dir / "source"
    output_dir = run_dir / "output"
    source_dir.mkdir()
    output_dir.mkdir()

    source_by_stem = {}
    for upload in uploaded_files:
        filename = Path(upload.filename or "").name
        if not filename.lower().endswith(".pdf"):
            continue

        target = unique_output_path(source_dir, filename)
        with target.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        source_by_stem[target.stem] = target

    if not source_by_stem:
        raise ValueError("No PDF files were uploaded.")

    created = 0
    missing_source = 0
    not_found_inside_pdf = 0
    total_visible_replacements = 0
    log = [f"Found {len(rows)} mapping rows.", f"Found {len(source_by_stem)} uploaded PDFs."]

    for old_text, new_text in rows:
        source_pdf = source_by_stem.get(old_text)
        output_name = safe_filename(new_text)
        output_pdf = unique_output_path(output_dir, output_name + ".pdf")

        if source_pdf is None:
            log.append(f"MISSING SOURCE PDF: {old_text}.pdf")
            missing_source += 1
            continue

        doc = fitz.open(source_pdf)
        replacements = []

        for page_index, page in enumerate(doc):
            for area in page.search_for(old_text):
                replacements.append((page_index, area))

        if not replacements:
            log.append(f"NOT FOUND INSIDE PDF: '{old_text}' in {source_pdf.name}")
            not_found_inside_pdf += 1
            doc.close()
            continue

        chosen_page_index, chosen_area = pick_one_position(replacements)

        for page_index, area in replacements:
            page = doc[page_index]
            redact_box = fitz.Rect(
                area.x0 - REDACT_PAD_LEFT,
                area.y0 - REDACT_PAD_TOP,
                area.x1 + REDACT_PAD_RIGHT,
                area.y1 + REDACT_PAD_BOTTOM,
            )
            page.add_redact_annot(redact_box, fill=(1, 1, 1))

        for page in doc:
            page.apply_redactions()

        page = doc[chosen_page_index]
        base_point = fitz.Point(chosen_area.x0, chosen_area.y1)
        text_point = apply_visual_offset(
            page,
            base_point,
            VISUAL_MOVE_RIGHT_POINTS,
            VISUAL_MOVE_DOWN_POINTS,
        )

        page.insert_text(
            text_point,
            new_text,
            fontsize=REPLACEMENT_FONT_SIZE,
            fontname=FONT_NAME,
            color=(0, 0, 0),
            rotate=page.rotation,
        )

        total_visible_replacements += 1
        doc.save(output_pdf, garbage=4, deflate=True)
        doc.close()

        created += 1
        log.append(f"Created: {output_pdf.name} from {source_pdf.name}")

    zip_path = run_dir / "edited-pdfs.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for pdf_path in sorted(output_dir.glob("*.pdf")):
            zf.write(pdf_path, pdf_path.name)

    log.extend(
        [
            "",
            "Finished.",
            f"Created PDFs: {created}",
            f"Missing source PDFs: {missing_source}",
            f"Numbers not found inside PDFs: {not_found_inside_pdf}",
            f"Total visible text replacements: {total_visible_replacements}",
        ]
    )

    RUNS[run_id] = {"dir": run_dir, "zip": zip_path}
    return {"id": run_id, "created": created, "log": log}


class PdfEditorHandler(BaseHTTPRequestHandler):
    server_version = "PDFNumberEditor/1.0"

    def do_HEAD(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(INDEX_HTML.encode("utf-8"))))
            self.end_headers()
            return
        self.send_error(404, "Not found")

    def do_GET(self):
        try:
            parsed = urlparse(self.path)

            if parsed.path == "/":
                self.send_html(INDEX_HTML)
                return

            if parsed.path == "/download":
                run_id = parse_qs(parsed.query).get("id", [""])[0]
                run = RUNS.get(run_id)
                if not run or not run["zip"].exists():
                    self.send_error(404, "Download not found")
                    return

                zip_path = run["zip"]
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", 'attachment; filename="edited-pdfs.zip"')
                self.send_header("Content-Length", str(zip_path.stat().st_size))
                self.end_headers()
                with zip_path.open("rb") as f:
                    shutil.copyfileobj(f, self.wfile)
                return

            self.send_error(404, "Not found")
        except Exception:
            log_error("GET request failed")
            raise

    def do_POST(self):
        if self.path != "/process":
            self.send_error(404, "Not found")
            return

        if fitz is None:
            self.send_json(
                {"error": "PyMuPDF is not installed. Run: python3 -m pip install -r requirements.txt"},
                status=500,
            )
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > MAX_UPLOAD_BYTES:
            self.send_json({"error": "Upload is too large."}, status=413)
            return

        try:
            body = self.rfile.read(content_length)
            mapping_text, pdf_fields = parse_multipart_form(self.headers, body)
            result = process_pdfs(pdf_fields, mapping_text)
            self.send_json(result)
        except Exception as exc:
            log_error("POST request failed")
            self.send_json({"error": str(exc)}, status=400)

    def send_html(self, content):
        encoded = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_json(self, content, status=200):
        encoded = json.dumps(content).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        message = "%s - - [%s] %s\n" % (
            self.address_string(),
            self.log_date_time_string(),
            format % args,
        )
        try:
            if sys.stderr:
                sys.stderr.write(message)
            else:
                with log_path().open("a", encoding="utf-8") as f:
                    f.write(message)
        except Exception:
            pass


def create_server():
    last_error = None
    for port in range(DEFAULT_APP_PORT, DEFAULT_APP_PORT + 20):
        try:
            return ThreadingHTTPServer((APP_HOST, port), PdfEditorHandler)
        except OSError as exc:
            last_error = exc
    raise last_error


def main():
    try:
        server = create_server()
        host, port = server.server_address
        url = f"http://{host}:{port}"
        if os.environ.get("PDF_EDITOR_OPEN_BROWSER", "1") != "0":
            threading.Timer(1.5, lambda: webbrowser.open(url)).start()

        log_info(f"PDF Number Editor running at {url}")
        log_info("Press Ctrl+C to stop.")
        server.serve_forever()
    except Exception:
        log_error("Application crashed")
        raise


if __name__ == "__main__":
    main()
