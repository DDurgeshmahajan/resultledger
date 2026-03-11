"""Debug: dump all 310xxx subject lines from paper list pages."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import pdfplumber
import re
import glob

pdfs = glob.glob("d:/result_ledger/uploads/*.pdf")
pdf_path = pdfs[0]

out = []
with pdfplumber.open(pdf_path) as pdf:
    for i in range(min(7, len(pdf.pages))):
        text = pdf.pages[i].extract_text()
        if not text:
            continue
        for line in text.split("\n"):
            line = line.strip()
            if re.match(r"310", line):
                out.append(f"P{i+1} |{line}|")

with open("d:/result_ledger/debug_310.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))

print(f"Wrote {len(out)} lines to debug_310.txt")
