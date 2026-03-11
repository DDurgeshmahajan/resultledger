"""Debug script to see actual raw text from the SPPU ledger PDF."""
import pdfplumber
import glob
import os

# Find any PDF in uploads folder
pdfs = glob.glob("d:/result_ledger/uploads/*.pdf")
if not pdfs:
    pdfs = glob.glob("d:/result_ledger/*.pdf")

if not pdfs:
    print("No PDF found!")
    exit()

pdf_path = pdfs[0]
print(f"=== Reading: {pdf_path} ===\n")

with pdfplumber.open(pdf_path) as pdf:
    total_pages = len(pdf.pages)
    print(f"Total pages: {total_pages}\n")

    # Find first page with PRN and print its raw text
    for i in range(total_pages):
        text = pdf.pages[i].extract_text()
        if text and "PRN" in text.upper():
            print(f"\n{'='*80}")
            print(f"PAGE {i+1} (FIRST STUDENT DATA PAGE)")
            print(f"{'='*80}")
            for j, line in enumerate(text.split("\n")):
                print(f"  L{j:03d}: |{line}|")

            # Also print next page
            if i+1 < total_pages:
                text2 = pdf.pages[i+1].extract_text()
                if text2:
                    print(f"\n{'='*80}")
                    print(f"PAGE {i+2}")
                    print(f"{'='*80}")
                    for j, line in enumerate(text2.split("\n")):
                        print(f"  L{j:03d}: |{line}|")
            break

    # Also print first 2 pages (paper list)
    for i in range(min(2, total_pages)):
        print(f"\n{'='*80}")
        print(f"PAGE {i+1} (PAPER LIST AREA)")
        print(f"{'='*80}")
        text = pdf.pages[i].extract_text()
        if text:
            for j, line in enumerate(text.split("\n")):
                print(f"  L{j:03d}: |{line}|")
