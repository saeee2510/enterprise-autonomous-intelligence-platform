from ingestion.loaders.txt_loader import load_text_file


doc = load_text_file(
    "ingestion/documents/support_logs/ticket_1001.txt"
)


print(doc)