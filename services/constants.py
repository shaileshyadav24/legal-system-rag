"""Shared constants for the query API."""

# Every legal dataset collection queried when no specific collection is requested.
# Each entry corresponds to a "<NAME>_docs" ChromaDB collection populated by dataset/dataset.py.
DATASETS = ["SCC", "FCA", "FC", "TCC", "CMAC", "CHRT", "SST", "RPD", "RAD", "RLLR", "ONCA"]
