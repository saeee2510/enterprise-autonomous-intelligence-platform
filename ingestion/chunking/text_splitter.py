from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_document(document):

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
        separators=[
            "\n\n",
            "\n",
            ".",
            " "
        ]
    )

    chunks = splitter.split_text(
        document["content"]
    )

    output = []

    for index, chunk in enumerate(chunks):

        output.append(
            {
                "content": chunk,
                "source": document["source"],
                "department": document["department"],
                "entity": document["entity"],
                "chunk_id": index
            }
        )

    return output