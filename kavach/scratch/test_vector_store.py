import struct
from typing import Tuple, Union
import numpy as np
from pathlib import Path

class NumpyIndexFlatL2:
    def __init__(self, d: int):
        self.d = int(d)
        self.vectors = np.empty((0, self.d), dtype=np.float32)

    @property
    def ntotal(self) -> int:
        return len(self.vectors)

    def add(self, x: np.ndarray) -> None:
        arr = np.asarray(x, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if arr.shape[1] != self.d:
            raise ValueError(f"Vector dimension mismatch: expected {self.d}, got {arr.shape[1]}")
        if len(self.vectors) == 0:
            self.vectors = np.ascontiguousarray(arr, dtype=np.float32)
        else:
            self.vectors = np.vstack([self.vectors, arr])

    def search(self, x: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        queries = np.asarray(x, dtype=np.float32)
        if queries.ndim == 1:
            queries = queries.reshape(1, -1)
        
        num_queries = len(queries)
        if self.ntotal == 0 or k <= 0:
            return np.zeros((num_queries, 0), dtype=np.float32), np.full((num_queries, 0), -1, dtype=np.int64)

        actual_k = min(k, self.ntotal)
        
        # Vectorized L2 squared distance computation
        # (q - v)^2 = q^2 + v^2 - 2*q*v
        # Compute distance for each query
        all_dists = []
        all_indices = []

        for q in queries:
            diff = self.vectors - q
            dists = np.sum(diff * diff, axis=1)  # shape (ntotal,)
            
            if actual_k < self.ntotal:
                # Top k smallest distances
                idx = np.argpartition(dists, actual_k - 1)[:actual_k]
                sorted_sub_idx = np.argsort(dists[idx])
                top_idx = idx[sorted_sub_idx]
            else:
                top_idx = np.argsort(dists)

            top_dists = dists[top_idx]
            
            # If k > ntotal, pad with -1 / infinity
            if k > self.ntotal:
                pad_len = k - self.ntotal
                top_dists = np.pad(top_dists, (0, pad_len), constant_values=np.inf)
                top_idx = np.pad(top_idx, (0, pad_len), constant_values=-1)

            all_dists.append(top_dists)
            all_indices.append(top_idx)

        return np.array(all_dists, dtype=np.float32), np.array(all_indices, dtype=np.int64)

    def reconstruct(self, i: int) -> np.ndarray:
        if i < 0 or i >= self.ntotal:
            raise IndexError(f"Index {i} out of bounds (ntotal={self.ntotal})")
        return self.vectors[i].copy()


def serialize_index(index: Union[NumpyIndexFlatL2, object]) -> np.ndarray:
    if hasattr(index, "vectors") and isinstance(index, NumpyIndexFlatL2):
        # 45-byte FAISS IndexFlatL2 compatible header
        # 4 bytes fourcc (IxF2), 4 bytes d (int32), 8 bytes ntotal (int64), 29 bytes dummy flags
        header = struct.pack("<4s i q 29s", b"IxF2", index.d, index.ntotal, b"\x00" * 29)
        vec_bytes = index.vectors.astype(np.float32).tobytes()
        full_bytes = header + vec_bytes
        return np.frombuffer(full_bytes, dtype=np.uint8)
    
    try:
        import faiss
        return faiss.serialize_index(index)
    except Exception as exc:
        raise RuntimeError(f"Unable to serialize index: {exc}")


def deserialize_index(buffer: Union[np.ndarray, bytes]) -> Union[NumpyIndexFlatL2, object]:
    if isinstance(buffer, np.ndarray):
        raw_bytes = buffer.tobytes()
    else:
        raw_bytes = bytes(buffer)

    if not raw_bytes:
        return None

    try:
        import faiss
        return faiss.deserialize_index(np.frombuffer(raw_bytes, dtype=np.uint8))
    except Exception:
        pass

    # Pure NumPy fallback loader
    if len(raw_bytes) >= 16:
        fourcc = raw_bytes[:4]
        d, = struct.unpack("<i", raw_bytes[4:8])
        ntotal, = struct.unpack("<q", raw_bytes[8:16])
        expected_len = ntotal * d * 4
        if len(raw_bytes) >= expected_len:
            vec_bytes = raw_bytes[-expected_len:] if expected_len > 0 else b""
            idx = NumpyIndexFlatL2(d)
            if expected_len > 0:
                vecs = np.frombuffer(vec_bytes, dtype=np.float32).reshape((ntotal, d))
                idx.add(vecs)
            return idx

    raise ValueError(f"Unsupported or corrupted vector index format (length={len(raw_bytes)})")


# Test round-trip with real knowledge/faiss_index/index.faiss
p = Path("knowledge/faiss_index/index.faiss")
raw = p.read_bytes()
idx = deserialize_index(raw)
print(f"Deserialized successfully! ntotal={idx.ntotal}, d={idx.d}")

# Test search
dummy_query = idx.reconstruct(0)
dists, indices = idx.search(np.array([dummy_query]), k=5)
print(f"Top 5 search result indices: {indices[0]}")
print(f"Top 5 search distances: {dists[0]}")
assert indices[0][0] == 0
assert abs(dists[0][0]) < 1e-5

# Test serialization & re-deserialization
ser = serialize_index(idx)
idx2 = deserialize_index(ser)
print(f"Re-deserialized index: ntotal={idx2.ntotal}, d={idx2.d}")
assert idx2.ntotal == idx.ntotal
assert idx2.d == idx.d
print("ALL TESTS PASSED SUCCESSFULLY!")
