from pathlib import Path


def load_text_file(file_path: str):

    path = Path(file_path)

    with open(path, "r", encoding="utf-8") as file:
        content = file.read()

    return {
        "content": content,
        "source": path.name,
        "department": path.parent.name,
        "entity": extract_entity(path.name)
    }


def extract_entity(filename):

    filename = filename.lower()

    if "ticket" in filename:
        return "support_issue"

    if "release" in filename:
        return "product_release"

    if "customer" in filename:
        return "customer_feedback"

    if "engineering" in filename:
        return "engineering_incident"

    return "unknown"