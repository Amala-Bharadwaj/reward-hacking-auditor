# Downloads the MBPP dataset, 974 Python problems with reference solutions and
# three published asserts each.

import urllib.request

URL = "https://raw.githubusercontent.com/google-research/google-research/master/mbpp/mbpp.jsonl"

data = urllib.request.urlopen(URL, timeout=60).read()
with open("data_mbpp.jsonl", "wb") as f:
    f.write(data)
print(f"Saved data_mbpp.jsonl, {len(data)} bytes")
