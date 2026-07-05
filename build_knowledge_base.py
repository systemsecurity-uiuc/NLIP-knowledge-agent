import json
import re
from io import BytesIO
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


OUT = Path("data/knowledge_base.json")
CHUNK_WORDS = 420
OVERLAP_WORDS = 70

SOURCES = [
    ("NLIP Project Website", "https://nlip-project.org/"),
    ("ECMA TC56 Webpage", "https://ecma-international.org/technical-committees/tc56/?tab=published-standards"),
    ("ECMA-430 Natural Language Interaction Protocol", "https://ecma-international.org/wp-content/uploads/ECMA-430_1st_edition_december_2025.pdf"),
    ("ECMA-431 NLIP over HTTP/HTTPS", "https://ecma-international.org/wp-content/uploads/ECMA-431_1st_edition_december_2025.pdf"),
    ("ECMA-432 NLIP over WebSocket", "https://ecma-international.org/wp-content/uploads/ECMA-432_1st_edition_december_2025.pdf"),
    ("ECMA-433 NLIP over AMQP", "https://ecma-international.org/wp-content/uploads/ECMA-433_1st_edition_december_2025.pdf"),
    ("ECMA-434 NLIP Security Profiles", "https://ecma-international.org/wp-content/uploads/ECMA-434_1st_edition_december_2025.pdf"),
    ("ECMA TR-113 NLIP Technical Report", "https://ecma-international.org/wp-content/uploads/ECMA_TR-113_1st_edition_december_2025.pdf"),
]

GITHUB_RAW_FILES = [
    ("NLIP Security Guidelines: README.md", "https://raw.githubusercontent.com/nlip-project/security_guidelines/main/README.md"),
    ("NLIP Security Guidelines: SECURITY.md", "https://raw.githubusercontent.com/nlip-project/security_guidelines/main/SECURITY.md"),
    ("NLIP Security Guidelines: CONTRIBUTING.md", "https://raw.githubusercontent.com/nlip-project/security_guidelines/main/CONTRIBUTING.md"),
    ("NLIP Security Guidelines: CODE_OF_CONDUCT.md", "https://raw.githubusercontent.com/nlip-project/security_guidelines/main/CODE_OF_CONDUCT.md"),
]


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fetch_text(url: str) -> str:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    if url.endswith(".pdf"):
        reader = PdfReader(BytesIO(response.content))
        return clean("\n".join(page.extract_text() or "" for page in reader.pages))

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return clean(soup.get_text(" "))


def chunk(source: str, url: str, text: str) -> list[dict[str, str]]:
    words = text.split()
    chunks = []
    start = 0
    index = 0
    while start < len(words):
        end = min(len(words), start + CHUNK_WORDS)
        body = " ".join(words[start:end])
        if body:
            chunks.append({
                "source": source,
                "url": url,
                "chunk": str(index),
                "text": body,
            })
        if end == len(words):
            break
        start = max(0, end - OVERLAP_WORDS)
        index += 1
    return chunks


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    all_chunks = []

    for source, url in SOURCES + GITHUB_RAW_FILES:
        print(f"Loading {source}")
        text = fetch_text(url)
        chunks = chunk(source, url, text)
        print(f"  chunks: {len(chunks)}")
        all_chunks.extend(chunks)

    OUT.write_text(json.dumps(all_chunks, indent=2))
    print(f"Wrote {len(all_chunks)} chunks to {OUT}")


if __name__ == "__main__":
    main()
