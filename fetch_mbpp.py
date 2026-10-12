import urllib.request

URL = "https://raw.githubusercontent.com/google-research/google-research/master/mbpp/mbpp.jsonl"

data = urllib.request.urlopen(URL, timeout=60).read()
with open("data_mbpp.jsonl", "wb") as f:
    f.write(data)
print(f"Saved data_mbpp.jsonl, {len(data)} bytes")
