import os
import csv
from pypdf import PdfReader

def extract_text_from_file(file_path: str) -> str:
    """
    Determines file extension and extracts content as a clean text string.
    Supports txt, pdf, csv, and standard programming code extensions.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found at: {file_path}")

    _, ext = os.path.splitext(file_path.lower())

    try:
        # 1. Parse PDF
        if ext == ".pdf":
            return parse_pdf(file_path)

        # 2. Parse CSV
        elif ext == ".csv":
            return parse_csv(file_path)

        # 3. Parse Plain Text / Source Code Files
        else:
            return parse_plain_text(file_path)

    except Exception as e:
        raise ValueError(f"Error parsing file '{os.path.basename(file_path)}': {str(e)}")

def parse_plain_text(file_path: str) -> str:
    """
    Reads plain text/code files (like .txt, .py, .js, .json, .md) with UTF-8 encoding.
    Falls back to 'ignore' for decoding errors to prevent binary crash.
    """
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def parse_pdf(file_path: str) -> str:
    """
    Extracts text page-by-page from PDF files using pypdf.
    """
    reader = PdfReader(file_path)
    extracted_text = []
    
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text()
        if page_text:
            extracted_text.append(page_text)
            
    if not extracted_text:
        return "[Empty PDF Document or Scanned Image PDF (no selectable text)]"
        
    return "\n--- Page Separator ---\n".join(extracted_text)

def parse_csv(file_path: str) -> str:
    """
    Parses CSV file and formats it as a neat readable text grid.
    """
    formatted_rows = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            # Limit rows to prevent blowing up the context window
            if i > 250:
                formatted_rows.append("[... CSV content truncated after 250 rows ...]")
                break
            formatted_rows.append(" | ".join(row))
            
    return "\n".join(formatted_rows)
