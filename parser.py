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
    # Remove common filler words
    stopwords = {"and", "of", "the", "in", "for", "to", "with", "using", "based", "on"}
    words = [w for w in name.strip().split() if w.lower() not in stopwords]

    if len(words) <= max_words:
        return " ".join(words)

    # Take initials of extra words
    abbr_parts = words[:2] + ["".join(w[0].upper() for w in words[2:])]
    return " ".join(abbr_parts)


def extract_subjects(pages, max_scan_pages: int = 10) -> dict:
    """
    Stage 1: Subject Identification
    Scans the first N pages for the Paper List section.
    Builds a dict mapping subject codes -> full subject names.
    """
    subjects = {}
    in_paper_list = False

    for page in pages[:max_scan_pages]:
        text = page.extract_text()
        if not text:
            continue

        for line in text.split("\n"):
            line = line.strip()

            # Detect the Paper List section header
            if re.search(r"paper\s*list|subject\s*list|course\s*list", line, re.IGNORECASE):
                in_paper_list = True
                continue

            # A 6-digit code followed by subject name
            match = re.match(r"(\d{6})\s+(.+)", line)
            if match:
                code = match.group(1)
                name = match.group(2).strip()

                # Clean trailing artifacts (page numbers, stray characters)
                name = re.sub(r"\s+\d+$", "", name)
                name = re.sub(r"\s{2,}", " ", name)

                if len(name) > 2:  # Ignore very short/corrupt names
                    subjects[code] = name
                    in_paper_list = True

            # If we're past the paper list and hit a PRN, stop scanning
            if in_paper_list and "PRN" in line:
                break

    logger.info(f"Identified {len(subjects)} subjects from paper list")
    return subjects


def find_student_pages_start(pages) -> int:
    """
    Determine where student records begin (after the Paper List).
    Returns the page index where student data starts.
    """
    for i, page in enumerate(pages):
        text = page.extract_text()
        if not text:
            continue
        if re.search(r"PRN\s*:", text):
            return i

    # Fallback: assume page 6 onwards
    return min(6, len(pages) - 1)


def parse_student_block(lines: list, subjects: dict) -> dict:
    """Parse a single student block from a list of text lines."""
    student = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # PRN extraction
        prn_match = re.search(r"PRN\s*:\s*(\S+)", line, re.IGNORECASE)
        if prn_match:
            student["PRN"] = prn_match.group(1)
            continue

        # Seat Number
        seat_match = re.search(r"SEAT\s*(?:NO|NUMBER)?\s*:\s*(\S+)", line, re.IGNORECASE)
        if seat_match:
            student["Seat No"] = seat_match.group(1)
            continue

        # Student Name (handles "NAME : ..." or "Student Name : ...")
        name_match = re.search(r"(?:STUDENT\s*)?NAME\s*:\s*(.+)", line, re.IGNORECASE)
        if name_match and "Mother" not in line:
            student["Name"] = name_match.group(1).strip()
            continue

        # Mother's Name
        mother_match = re.search(r"MOTHER(?:\s*'?S)?\s*(?:NAME)?\s*:\s*(.+)", line, re.IGNORECASE)
        if mother_match:
            student["Mother Name"] = mother_match.group(1).strip()
            continue

        # SGPA
        sgpa_match = re.search(r"SGPA\s*:\s*([\d.]+)", line, re.IGNORECASE)
        if sgpa_match:
            student["SGPA"] = sgpa_match.group(1)
            continue

        # CGPA (if present)
        cgpa_match = re.search(r"CGPA\s*:\s*([\d.]+)", line, re.IGNORECASE)
        if cgpa_match:
            student["CGPA"] = cgpa_match.group(1)
            continue

        # Result status
        result_match = re.search(r"RESULT\s*:\s*(.+)", line, re.IGNORECASE)
        if result_match:
            student["Result"] = result_match.group(1).strip()
            continue

        # Subject marks line: starts with 6-digit code
        subj_match = re.match(r"(\d{6})\s+(.+)", line)
        if subj_match:
            code = subj_match.group(1)
            rest = subj_match.group(2)

            # Extract all numbers from the line
            numbers = re.findall(r"\d+", rest)

            if code in subjects and numbers:
                # The total marks is typically the last standalone number
                # or at a specific position. We use a heuristic:
                # In SPPU ledgers, the marks line usually has:
                # code | ... | ISE | ESE | Total | Grade | GP | Credits | CxG
                # We want "Total" which is usually in the middle area.
                # Safer heuristic: pick the number that is likely "total"
                # Usually it's the 3rd-to-last or we look at position.
                total = extract_total_marks(numbers)
                col_name = f"{code}_{abbreviate_subject(subjects[code])}_Total"
                student[col_name] = total

    return student


def extract_total_marks(numbers: list) -> str:
    """
    Extract total marks from a list of numbers found on a subject line.
    SPPU format typically: ISE ESE Total Grade GP Credits CxG
    We need the Total which is usually the 3rd number from the back
    when there are enough numbers, or we use a position-based heuristic.
    """
    if len(numbers) >= 5:
        # Standard format: ... ISE ESE Total GradePoints Credits CxGP
        # Total is at index -5 (5th from end) in many SPPU ledgers
        return numbers[-5]
    elif len(numbers) >= 3:
        # Shorter format: pick middle-ish value
        return numbers[-3]
    elif len(numbers) >= 1:
        return numbers[-1]
    return "N/A"


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
        current_lines = []
        has_prn = False

        for page in all_pages[start_page:]:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                # Check if this line starts a new student block
                if re.search(r"PRN\s*:", line, re.IGNORECASE):
                    # Save previous student if exists
                    if has_prn and current_lines:
                        student = parse_student_block(current_lines, subjects)
                        if student.get("PRN"):
                            students.append(student)

                    # Start new block
                    current_lines = [line]
                    has_prn = True
                else:
                    if has_prn:
                        current_lines.append(line)

        # Don't forget the last student
        if has_prn and current_lines:
            student = parse_student_block(current_lines, subjects)
            if student.get("PRN"):
                students.append(student)

    logger.info(f"Extracted {len(students)} student records")

    if not students:
        # Return empty DataFrame with basic columns
        return pd.DataFrame(columns=["PRN", "Seat No", "Name", "Mother Name", "SGPA", "Result"])

    df = pd.DataFrame(students)

    # Reorder columns: identification first, then subjects, then results
    id_cols = ["PRN", "Seat No", "Name", "Mother Name"]
    result_cols = ["SGPA", "CGPA", "Result"]
    subject_cols = [c for c in df.columns if c not in id_cols + result_cols]
    subject_cols.sort()  # Sort by subject code

    ordered_cols = [c for c in id_cols if c in df.columns]
    ordered_cols += subject_cols
    ordered_cols += [c for c in result_cols if c in df.columns]

    df = df.reindex(columns=ordered_cols)

    return df