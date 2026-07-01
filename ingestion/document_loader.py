from pathlib import Path


SUPPORTED_EXTENSIONS = {".txt", ".md"}


def load_documents(directory: str):
    docs = []

    for path in Path(directory).rglob("*"):
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            docs.append(
                {
                    "source": str(path),
                    "content": path.read_text(encoding="utf-8"),
                }
            )

    return docs