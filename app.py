"""
SPPU Result Ledger Extractor — Flask Backend
Designed by Durgesh Mahajan

POST /extract  →  multipart/form-data (file: ledger.pdf)  →  <pdf_name>.xlsx
"""

from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import os
import uuid
import logging
from pdf_parser import parse_students
from utils import brand_excel, get_output_filename

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/extract", methods=["POST"])
def extract():
    # --- Validation ---
    if "file" not in request.files:
        return jsonify({"error": "No file provided. Please upload a PDF file."}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Only PDF files are accepted."}), 400

    # Check file size
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({"error": "File too large. Maximum size is 50 MB."}), 413

    # --- Processing ---
    try:
        # Save with unique name to avoid conflicts
        unique_id = uuid.uuid4().hex[:8]
        safe_filename = f"{unique_id}_{file.filename}"
        pdf_path = os.path.join(UPLOAD_FOLDER, safe_filename)
        file.save(pdf_path)

        logger.info(f"Processing file: {file.filename}")

        # Parse the PDF
        df = parse_students(pdf_path)

        if df.empty:
            # Cleanup
            os.remove(pdf_path)
            return jsonify({
                "error": "No student records found in the PDF. "
                         "Please ensure this is a valid SPPU result ledger."
            }), 422

        # Generate output Excel
        output_name = get_output_filename(file.filename)
        output_path = os.path.join(OUTPUT_FOLDER, f"{unique_id}_{output_name}")
        df.to_excel(output_path, index=False, engine="openpyxl")

        # Apply branding
        brand_excel(output_path)

        logger.info(f"Successfully extracted {len(df)} students → {output_name}")

        # Send file and cleanup
        response = send_file(
            output_path,
            as_attachment=True,
            download_name=output_name,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # Cleanup uploaded PDF after response (deferred)
        @response.call_on_close
        def cleanup():
            try:
                os.remove(pdf_path)
                os.remove(output_path)
            except OSError:
                pass

        return response

    except Exception as e:
        logger.exception("Error processing PDF")
        return jsonify({
            "error": f"Failed to process the PDF: {str(e)}"
        }), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "SPPU Result Ledger Extractor"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)