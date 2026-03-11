"""Quick test to verify parser output."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from pdf_parser import parse_students
import glob

pdfs = glob.glob("d:/result_ledger/uploads/*.pdf")
if not pdfs:
    print("No PDF found!")
    exit()

df = parse_students(pdfs[0])
print(f"Total students: {len(df)}")
print(f"\nColumns ({len(df.columns)}):")
for c in df.columns:
    print(f"  - {c}")

print(f"\nFirst 3 students:")
if len(df) > 0:
    for i in range(min(3, len(df))):
        row = df.iloc[i]
        print(f"\n  Student {i+1}:")
        print(f"    Seat No: {row.get('Seat No', 'MISSING')}")
        print(f"    PRN: {row.get('PRN', 'MISSING')}")
        print(f"    Name: {row.get('Name', 'MISSING')}")
        print(f"    Mother Name: {row.get('Mother Name', 'MISSING')}")
        print(f"    SGPA: {row.get('SGPA', 'MISSING')}")
        # Print first subject total + grade
        for c in df.columns:
            if 'Total' in c:
                print(f"    {c}: {row.get(c, 'N/A')}")
                break
        for c in df.columns:
            if 'Grade' in c:
                print(f"    {c}: {row.get(c, 'N/A')}")
                break
