#!/usr/bin/env python3

"""
Generate Academic Pages publication Markdown files from publications.tsv.

Expected TSV columns:
    pub_date
    title
    venue
    excerpt
    citation
    url_slug
    paper_url
    category

Supported categories:
    manuscripts   -> Journal Articles
    conferences   -> Conference Papers
    books         -> Books / Book Chapters

The script:
1. Reads publications.tsv
2. Scans existing files in _publications/
3. Skips publications whose titles already exist
4. Generates only missing publication Markdown files
5. Uses filenames such as:
       2025-aime-ms-speech.md
       2021-caida-lung-cancer.md
"""

import csv
import re
import sys
import unicodedata
from pathlib import Path


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

TSV_FILE = SCRIPT_DIR / "publications.tsv"
PUBLICATIONS_DIR = REPO_ROOT / "_publications"


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

VALID_CATEGORIES = {
    "manuscripts",
    "conferences",
    "books",
}


# These are optional aliases for publications you already
# created manually. They are not strictly necessary because
# the script also checks titles, but keeping them here gives
# another layer of protection against duplicates.
EXISTING_FILENAME_ALIASES = {
    "glstm": "2024-glstm.md",
    "acm-bcb-parkinson": "2026-acm-bcb-parkinson.md",
    "bspc-cgm-review": "2026-bspc-cgm-review.md",
    "eusipco-meal-detection": "2026-eusipco-meal-detection.md",
}


# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------

def normalize_title(text):
    """
    Normalize titles so that minor punctuation/case differences
    do not create duplicate publications.
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = text.lower()

    # Normalize apostrophes and quotation marks.
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("–", "-")
        .replace("—", "-")
    )

    # Remove punctuation for comparison.
    text = re.sub(r"[^a-z0-9]+", " ", text)

    return " ".join(text.split())


def yaml_escape(value):
    """
    Escape text for a YAML double-quoted string.
    """
    if value is None:
        return ""

    value = str(value)
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = value.replace("\r", " ")
    value = value.replace("\n", " ")

    return value.strip()


def clean_slug(slug):
    """
    Convert a slug to a safe filename/permalink component.
    """
    slug = slug.strip().lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def extract_front_matter_title(path):
    """
    Read the title field from an existing Markdown publication.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return None

    # Only inspect YAML front matter.
    if not content.startswith("---"):
        return None

    parts = content.split("---", 2)

    if len(parts) < 3:
        return None

    front_matter = parts[1]

    match = re.search(
        r'^\s*title\s*:\s*["\']?(.*?)["\']?\s*$',
        front_matter,
        re.MULTILINE,
    )

    if match:
        return match.group(1).strip()

    return None


def load_existing_publications():
    """
    Scan _publications and collect filenames and normalized titles.
    """
    existing_files = set()
    existing_titles = set()

    if not PUBLICATIONS_DIR.exists():
        PUBLICATIONS_DIR.mkdir(parents=True, exist_ok=True)

    for md_file in PUBLICATIONS_DIR.glob("*.md"):
        existing_files.add(md_file.name.lower())

        title = extract_front_matter_title(md_file)

        if title:
            existing_titles.add(normalize_title(title))

    return existing_files, existing_titles


def validate_row(row, row_number):
    """
    Validate one TSV row.
    """
    required = [
        "pub_date",
        "title",
        "venue",
        "citation",
        "url_slug",
        "category",
    ]

    missing = []

    for field in required:
        if not row.get(field, "").strip():
            missing.append(field)

    if missing:
        raise ValueError(
            f"Row {row_number}: missing required field(s): "
            + ", ".join(missing)
        )

    category = row["category"].strip()

    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Row {row_number}: invalid category '{category}'. "
            f"Use one of: {', '.join(sorted(VALID_CATEGORIES))}"
        )

    date = row["pub_date"].strip()

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError(
            f"Row {row_number}: pub_date must use YYYY-MM-DD. "
            f"Found: {date}"
        )


def build_markdown(row):
    """
    Build the Markdown content expected by Academic Pages.
    """

    pub_date = row["pub_date"].strip()
    title = yaml_escape(row["title"])
    venue = yaml_escape(row["venue"])
    excerpt = row.get("excerpt", "").strip()
    citation = yaml_escape(row["citation"])
    paper_url = row.get("paper_url", "").strip()
    category = row["category"].strip()
    slug = clean_slug(row["url_slug"])

    lines = [
        "---",
        f'title: "{title}"',
        "collection: publications",
        f"category: {category}",
        f"permalink: /publication/{pub_date[:4]}-{slug}",
        f"date: {pub_date}",
        f'venue: "{venue}"',
    ]

    if paper_url:
        lines.append(f'paperurl: "{yaml_escape(paper_url)}"')

    lines.append(f'citation: "{citation}"')
    lines.append("---")
    lines.append("")

    if excerpt:
        lines.append(excerpt.strip())
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------
# Main generator
# ---------------------------------------------------------

def main():

    print("=" * 70)
    print("Academic Pages Publication Generator")
    print("=" * 70)

    if not TSV_FILE.exists():
        print(f"\nERROR: TSV file not found:")
        print(TSV_FILE)
        sys.exit(1)

    PUBLICATIONS_DIR.mkdir(parents=True, exist_ok=True)

    existing_files, existing_titles = load_existing_publications()

    print(f"\nTSV file:")
    print(f"  {TSV_FILE}")

    print(f"\nPublication directory:")
    print(f"  {PUBLICATIONS_DIR}")

    print(
        f"\nExisting Markdown publications detected: "
        f"{len(existing_files)}"
    )

    created = []
    skipped = []
    errors = []

    with TSV_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as infile:

        reader = csv.DictReader(infile, delimiter="\t")

        expected_columns = {
            "pub_date",
            "title",
            "venue",
            "excerpt",
            "citation",
            "url_slug",
            "paper_url",
            "category",
        }

        if reader.fieldnames is None:
            print("\nERROR: TSV has no header.")
            sys.exit(1)

        actual_columns = set(reader.fieldnames)

        missing_columns = expected_columns - actual_columns

        if missing_columns:
            print(
                "\nERROR: publications.tsv is missing columns:"
            )

            for column in sorted(missing_columns):
                print(f"  - {column}")

            sys.exit(1)

        for row_number, row in enumerate(reader, start=2):

            # Ignore completely empty TSV rows.
            if not any(
                (value or "").strip()
                for value in row.values()
            ):
                continue

            try:
                validate_row(row, row_number)

                pub_date = row["pub_date"].strip()
                year = pub_date[:4]

                title = row["title"].strip()
                normalized_title = normalize_title(title)

                slug = clean_slug(row["url_slug"])

                filename = f"{year}-{slug}.md"
                output_path = PUBLICATIONS_DIR / filename

                # -------------------------------------------------
                # Duplicate check 1:
                # Existing manually created title
                # -------------------------------------------------

                if normalized_title in existing_titles:

                    skipped.append(
                        (
                            filename,
                            "publication title already exists"
                        )
                    )

                    print(
                        f"SKIP   {title}\n"
                        f"       Reason: title already exists"
                    )

                    continue

                # -------------------------------------------------
                # Duplicate check 2:
                # Known manually-created filename
                # -------------------------------------------------

                alias_filename = EXISTING_FILENAME_ALIASES.get(slug)

                if (
                    alias_filename
                    and alias_filename.lower() in existing_files
                ):

                    skipped.append(
                        (
                            filename,
                            f"existing file {alias_filename}"
                        )
                    )

                    print(
                        f"SKIP   {title}\n"
                        f"       Reason: {alias_filename} already exists"
                    )

                    continue

                # -------------------------------------------------
                # Duplicate check 3:
                # Generated filename already exists
                # -------------------------------------------------

                if filename.lower() in existing_files:

                    skipped.append(
                        (
                            filename,
                            "target filename already exists"
                        )
                    )

                    print(
                        f"SKIP   {title}\n"
                        f"       Reason: {filename} already exists"
                    )

                    continue

                # -------------------------------------------------
                # Generate publication
                # -------------------------------------------------

                markdown = build_markdown(row)

                output_path.write_text(
                    markdown,
                    encoding="utf-8"
                )

                created.append(filename)

                # Immediately register the new publication so that
                # duplicated TSV rows cannot create another copy.
                existing_files.add(filename.lower())
                existing_titles.add(normalized_title)

                print(
                    f"CREATE {filename}\n"
                    f"       {title}"
                )

            except Exception as exc:

                errors.append(
                    (
                        row_number,
                        row.get("title", ""),
                        str(exc),
                    )
                )

                print(
                    f"ERROR  TSV row {row_number}: "
                    f"{row.get('title', '')}"
                )

                print(f"       {exc}")

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("Generation complete")
    print("=" * 70)

    print(f"\nCreated: {len(created)}")

    for filename in created:
        print(f"  + {filename}")

    print(f"\nSkipped: {len(skipped)}")

    for filename, reason in skipped:
        print(f"  = {filename} ({reason})")

    print(f"\nErrors: {len(errors)}")

    for row_number, title, error in errors:
        print(
            f"  ! Row {row_number}: {title}\n"
            f"    {error}"
        )

    if errors:
        print(
            "\nSome publications were not generated. "
            "Fix the listed TSV rows and run the script again."
        )
        sys.exit(1)

    print(
        "\nSuccess. Only missing publications were generated."
    )


if __name__ == "__main__":
    main()
