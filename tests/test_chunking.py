from ingestion.loaders.txt_loader import load_text_file
from ingestion.chunking.text_splitter import split_document


document = load_text_file(
    "ingestion/documents/meeting_notes/engineering_review.txt"
)


chunks = split_document(document)


print(
    "Number of chunks:",
    len(chunks)
)


for chunk in chunks:

    print("\n--- CHUNK ---")

    print(chunk)