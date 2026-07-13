import json

from ingestion.search import ask  # your existing CLI pipeline


def process_query(query: str):

    # ask() currently prints + returns nothing → we need to modify it slightly
    # so here we assume you refactor ask() to RETURN structured output

    result = ask(query)

    return result