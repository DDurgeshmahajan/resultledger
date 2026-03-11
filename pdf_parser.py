"""
SPPU Result Ledger Parser
Designed by Durgesh Mahajan

Robust multi-stage pipeline to extract structured student data
from Savitribai Phule Pune University result ledger PDFs.
"""

import pdfplumber
import re
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def abbreviate_subject(name: str, max_words: int = 4) -> str:
    """Create a readable abbreviation from a subject name."""
    stopwords = {"and", "of", "the", "in", "for", "to", "with", "using", "based", "on"}
    words = [w for w in name.strip().split() if w.lower() not in stopwords]

    if len(words) <= max_words:
        return " ".join(words)

    abbr_parts = words[:2] + ["".join(w[0].upper() for w in words[2:])]
    return " ".join(abbr_parts)


def extract_subjects(pages, max_scan_pages: int = 10) -> dict:
    """
    Stage 1: Subject Identification
    Scans the Paper List pages. Supports two code formats:
      Old (pre-2024):  210241 210241 DISCRETE MATHEMATICS
                       310241 DESIGN AND ANALYSIS OF ALGORITHMS
      New (2024 NEP):  PCC-201-COM Data Structures
                       EEM-231-COM Entrepreneurship Development
    """
    subjects = {}

    # Regex for new-style alphanumeric codes: PCC-201-COM, BSC-101-BES_TW, etc.
    new_code_re = re.compile(
        r"^([A-Za-z][A-Za-z0-9\-]+(?:_\w+)?)\s+([A-Za-z][A-Za-z &(),\-/.']+.*)$"
    )

    for page in pages[:max_scan_pages]:
        text = page.extract_text()
        if not text:
            continue

        for line in text.split("\n"):
            line = line.strip()

            # Skip header / metadata lines
            if not line or line.startswith("Code ") or line.startswith("continued"):
                continue
            if line.startswith("Savitribai") or line.startswith("Pune-"):
                continue
            if line.startswith("Paper List") or line.startswith("S.E."):
                continue
            if line.startswith("[") or line.startswith("Semester:"):
                continue

            # ── Old format: CODE CODE SUBJECT_NAME (code repeated) ──
            # e.g. "210241 210241 DISCRETE MATHEMATICS"
            match = re.match(r"(\d{6}\w*)\s+\1\s+(.+)", line)
            if match:
                code = match.group(1)
                name = match.group(2).strip()
                name = re.sub(r"\s{2,}", " ", name)
                if len(name) > 2:
                    subjects[code] = name
                continue

            # ── Old format: CODE SUBJECT_NAME (6-digit, not repeated) ──
            # e.g. "310245A INTERNET OF THINGS"
            match2 = re.match(r"(\d{6}\w*(?:_\w+)?)\s+([A-Za-z][A-Za-z &(),\-/.']+.*)$", line)
            if match2:
                code = match2.group(1)
                name = match2.group(2).strip()
                name = re.sub(r"\s+\d+$", "", name)
                name = re.sub(r"\s{2,}", " ", name)
                if len(name) > 2 and not re.match(r"^\d+$", name):
                    subjects[code] = name
                continue

            # ── New format: ALPHA-CODE SUBJECT_NAME ──
            # e.g. "PCC-201-COM Data Structures"
            match3 = new_code_re.match(line)
            if match3:
                code = match3.group(1)
                name = match3.group(2).strip()
                name = re.sub(r"\s+\d+$", "", name)
                name = re.sub(r"\s{2,}", " ", name)
                if len(name) > 2 and not re.match(r"^\d+$", name):
                    subjects[code] = name

    logger.info(f"Identified {len(subjects)} subjects from paper list")
    return subjects


def find_student_pages_start(pages) -> int:
    """Find the first page containing student records (PRN:)."""
    for i, page in enumerate(pages):
        text = page.extract_text()
        if not text:
            continue
        if re.search(r"PRN\s*:", text):
            return i
    return min(6, len(pages) - 1)


def parse_student_line(line: str) -> dict:
    """
    Parse the combined PRN/Seat/Name/Mother line.
    Format:
      PRN: 72444929K SEAT NO.: T400300239 NAME: ABHIRAJ SACHIN KANASE Mother's Name :- UJJWALA SACHIN KANASE
    """
    student = {}

    prn_match = re.search(r"PRN\s*:\s*(\S+)", line, re.IGNORECASE)
    if prn_match:
        student["PRN"] = prn_match.group(1)

    seat_match = re.search(r"SEAT\s*NO\.?\s*:?\s*(\S+)", line, re.IGNORECASE)
    if seat_match:
        student["Seat No"] = seat_match.group(1)

    # NAME comes after "NAME:" and before "Mother"
    name_match = re.search(r"NAME\s*:\s*(.+?)(?:\s+Mother)", line, re.IGNORECASE)
    if name_match:
        student["Name"] = name_match.group(1).strip()
    else:
        # Fallback: NAME: ... (until end of line)
        name_match2 = re.search(r"NAME\s*:\s*(.+)", line, re.IGNORECASE)
        if name_match2:
            student["Name"] = name_match2.group(1).strip()

    # Mother's Name :- ...
    mother_match = re.search(r"Mother(?:'s)?\s*Name\s*:?-?\s*(.+)", line, re.IGNORECASE)
    if mother_match:
        student["Mother Name"] = mother_match.group(1).strip()

    return student


def parse_subject_line(line: str, subjects: dict) -> tuple:
    """
    Parse a subject marks line. Format examples:
      Old: 310241 * 052 * 019 --- --- --- --- --- --- --- --- 071 3 3 A+ 9 27
      New: PCC-201-COM * 028 * 046 --- --- --- --- --- --- --- --- --- 074 3 3 A 8 24

    Returns (subject_code, total_marks, grade) or None.
    """
    # Match subject code at start:
    #   Old: 6 digits + optional suffix (310241, 310250B, 310241_PR)
    #   New: alphanumeric with hyphens (PCC-201-COM, CEP-241-COM_TW)
    match = re.match(r"([A-Za-z0-9][A-Za-z0-9\-]*(?:_\w+)?)\s+(.+)", line)
    if not match:
        return None
    
    code = match.group(1)
    # Verify this looks like a subject code, not random text
    # Must contain at least one digit and either be all-digits or contain a hyphen
    if not re.search(r"\d", code):
        return None
    if not (re.match(r"\d{6}", code) or "-" in code):
        return None

    rest = match.group(2).strip()

    # Skip *"AC" lines (audit course / non-countable)
    if '"AC"' in rest or "'AC'" in rest:
        return None

    # Extract all tokens from the rest of the line
    tokens = rest.split()

    # Find the "Tot" value: it's the first number that appears after the
    # marks columns (ESE, ISE, TW, etc.) and ---/AAA/* markers.
    # In the SPPU format, after all the component columns, we get:
    # Tot Crd Ern Grd GrdPnt CrdPnt
    # The total is typically a 2-3 digit number that appears right before
    # a sequence of small numbers (credits) and grade letters.

    # Strategy: collect all pure numeric tokens
    numeric_positions = []
    for i, tok in enumerate(tokens):
        if re.match(r"^\d+$", tok):
            numeric_positions.append((i, int(tok)))

    if not numeric_positions:
        return None

    # The "total" is the larger number that comes after the marks components.
    # In SPPU format, the total appears right before Credits (small numbers 1-3).
    # We look for the pattern: Total(big) Credits(small) Earned(small) Grade ...
    total = None
    grade = None

    for idx in range(len(numeric_positions)):
        pos_i, val_i = numeric_positions[idx]

        # If this value could be a total (reasonable range 0-200)
        # and the next numeric value is small (credits: 0-10), this is likely the total
        if idx + 1 < len(numeric_positions):
            pos_next, val_next = numeric_positions[idx + 1]
            if val_next <= 10 and val_i >= 0:
                # Check if there's a grade nearby (letter after credits)
                total = str(val_i)
                # Look for grade: A+, A, B+, B, C, P, F, O, etc.
                # Grade appears a couple tokens after the total
                for g_offset in range(1, 6):
                    g_pos = pos_i + g_offset
                    if g_pos < len(tokens):
                        g_tok = tokens[g_pos]
                        if re.match(r"^(O|A\+?|B\+?|C|P|F|FFF|AC|ACN)$", g_tok):
                            grade = g_tok
                            break
                break

    if total is None and numeric_positions:
        # Fallback: just take the last big number
        for pos_i, val_i in reversed(numeric_positions):
            if val_i >= 10:
                total = str(val_i)
                break
        if total is None:
            total = str(numeric_positions[-1][1])

    # Find grade if not found yet
    if grade is None:
        for tok in tokens:
            if re.match(r"^(O|A\+?|B\+?|C|P|F|FFF)$", tok):
                grade = tok
                break

    return (code, total, grade)


def parse_sgpa_line(line: str) -> dict:
    """
    Parse SGPA line. Format:
      SGPA: (5) 8.05
      or within: Fifth Semester SGPA : 8.05 Credits Earned/Total : 21/21
    """
    result = {}

    sgpa_match = re.search(r"SGPA\s*:?\s*(?:\(\d+\))?\s*([\d.]+|-----)", line, re.IGNORECASE)
    if sgpa_match:
        val = sgpa_match.group(1)
        if val != "-----":
            result["SGPA"] = val

    credits_match = re.search(r"Credits\s*Earned/Total\s*:\s*(\d+/\d+)", line, re.IGNORECASE)
    if credits_match:
        result["Credits Earned"] = credits_match.group(1)

    return result


def parse_students(pdf_path: str) -> pd.DataFrame:
    """
    Main extraction pipeline.
    Returns a DataFrame with one row per student.
    """
    students = []

    with pdfplumber.open(pdf_path) as pdf:
        all_pages = pdf.pages

        # Stage 1: Extract subject mappings
        subjects = extract_subjects(all_pages)

        if not subjects:
            logger.warning("No subjects found in paper list. Attempting full scan.")
            subjects = extract_subjects(all_pages, max_scan_pages=len(all_pages))

        # Stage 2: Find where student data begins
        start_page = find_student_pages_start(all_pages)
        logger.info(f"Student data begins at page {start_page + 1}")

        # Stage 3: Parse all student blocks
        current_student = None

        for page in all_pages[start_page:]:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue

                # ── New student block: PRN line ──
                if re.search(r"PRN\s*:", line, re.IGNORECASE):
                    # Save previous student
                    if current_student and current_student.get("PRN"):
                        students.append(current_student)

                    # Parse the combined info line
                    current_student = parse_student_line(line)
                    continue

                if current_student is None:
                    continue

                # ── Skip header/separator lines ──
                if line.startswith("~~~") or line.startswith("..."):
                    continue
                if line.startswith("SAVITRIBAI") or line.startswith("PUNE-"):
                    continue
                if "College Ledger" in line or "PunCode" in line:
                    continue
                if line.startswith("ESE ") or line.startswith("Min ") or line.startswith("Max "):
                    continue
                if line.startswith("Branch") or line.startswith("Page "):
                    continue

                # ── SEMESTER line ──
                sem_match = re.match(r"SEMESTER\s*:\s*(\d+)", line, re.IGNORECASE)
                if sem_match:
                    current_student["Semester"] = sem_match.group(1)
                    continue

                # ── SGPA / Credits line ──
                if "SGPA" in line.upper():
                    sgpa_data = parse_sgpa_line(line)
                    current_student.update(sgpa_data)
                    continue

                # ── Result line ──
                result_match = re.search(r"RESULT\s*:\s*(.+)", line, re.IGNORECASE)
                if result_match:
                    current_student["Result"] = result_match.group(1).strip()
                    continue

                # ── Subject marks line ──
                # Old format: starts with 6-digit code (310241)
                # New format: starts with alpha-code (PCC-201-COM)
                subj_match = re.match(r"(?:\d{6}|[A-Z][A-Za-z0-9\-]+)", line)
                if subj_match and not line.startswith("SAVITRIBAI") and not line.startswith("SEMESTER") and not line.startswith("RESULT") and not line.startswith("SGPA") and not line.startswith("Page ") and not line.startswith("Branch") and not line.startswith("College") and not line.startswith("PunCode") and not line.startswith("PUNE") and not line.startswith("MEDIUM"):
                    parsed = parse_subject_line(line, subjects)
                    if parsed:
                        code, total, grade = parsed
                        subj_name = subjects.get(code, code)
                        # Use subject name in column header for clarity
                        col_total = f"{code} {subj_name} Total"
                        col_grade = f"{code} {subj_name} Grade"
                        current_student[col_total] = total
                        if grade:
                            current_student[col_grade] = grade

        # Don't forget the last student
        if current_student and current_student.get("PRN"):
            students.append(current_student)

    logger.info(f"Extracted {len(students)} student records")

    if not students:
        return pd.DataFrame(columns=["Seat No", "PRN", "Name", "Mother Name", "SGPA", "Result"])

    df = pd.DataFrame(students)

    # ── Reorder columns ──
    # Priority: Seat No, PRN, Name, Mother Name, Semester, then subjects, then SGPA/Credits/Result
    id_cols = ["Seat No", "PRN", "Name", "Mother Name", "Semester"]
    summary_cols = ["SGPA", "Credits Earned", "Result"]

    # Subject columns: sort by code
    subject_cols = [c for c in df.columns if c not in id_cols + summary_cols]
    subject_cols.sort()

    ordered = [c for c in id_cols if c in df.columns]
    ordered += subject_cols
    ordered += [c for c in summary_cols if c in df.columns]

    df = df.reindex(columns=ordered)

    return df