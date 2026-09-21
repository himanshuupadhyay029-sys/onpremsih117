from pathlib import Path
import struct
import numpy as np

p = Path("knowledge/faiss_index/index.faiss")
b = p.read_bytes()
fourcc = b[:4]
d, = struct.unpack("<i", b[4:8])
ntotal, = struct.unpack("<q", b[8:16])
print(f"Fourcc: {fourcc}, d: {d}, ntotal: {ntotal}")

expected_data_len = ntotal * d * 4
print(f"Expected data len: {expected_data_len}, File len: {len(b)}")

# In FAISS IndexFlat, the vectors are at the end of the file: b[-expected_data_len:]
raw_vecs = b[-expected_data_len:]
vectors = np.frombuffer(raw_vecs, dtype=np.float32).reshape((ntotal, d))
print("Extracted vectors shape:", vectors.shape)
print("Vector 0 norm:", np.linalg.norm(vectors[0]))
print("Vector 0 first 5 elements:", vectors[0][:5])
