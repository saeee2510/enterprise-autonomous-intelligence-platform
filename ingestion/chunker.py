from langchain_text_splitters import RecursiveCharacterTextSplitter


splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100,
)


def chunk_documents(documents):
    chunks = []

    for doc in documents:
        pieces = splitter.split_text(doc["content"])

        for piece in pieces:
            chunks.append(
                {
                    "source": doc["source"],
                    "content": piece,
                }
            )

    return chunks