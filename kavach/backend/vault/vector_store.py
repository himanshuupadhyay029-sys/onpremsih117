"""vector_store.py — Resilient Vector Index & Storage for KAVACH Knowledge Vault.

Provides high-performance flat vector indexing (L2 Euclidean distance).
Supports native FAISS when available, with an automatic, zero-dependency,
pure-NumPy fallback engine if native C++ binaries are blocked by OS security
policies (e.g. Windows Defender Application Control / Smart App Control).
"""

import logging
import struct
from typing import Optional, Tuple, Union
import numpy as np

logger = logging.getLogger("kavach.vector_store")

try:
    import faiss
    _FAISS_AVAILABLE = True
except Exception as exc:
    faiss = None
    _FAISS_AVAILABLE = False
    logger.info(f"Native FAISS library not available ({exc}); using optimized NumPy vector store fallback.")


class NumpyIndexFlatL2:
    """Pure NumPy implementation of IndexFlatL2 with exact L2 squared distance."""

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
        all_dists = []
        all_indices = []

        for q in queries:
            diff = self.vectors - q
            dists = np.sum(diff * diff, axis=1)  # shape (ntotal,)

            if actual_k < self.ntotal:
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


def IndexFlatL2(d: int):
    """Factory creating a FAISS IndexFlatL2 or NumpyIndexFlatL2 depending on environment."""
    if _FAISS_AVAILABLE and faiss is not None:
        try:
            return faiss.IndexFlatL2(int(d))
        except Exception:
            pass
    return NumpyIndexFlatL2(int(d))


def serialize_index(index: Union[NumpyIndexFlatL2, object]) -> np.ndarray:
    """Serializes vector index to uint8 byte buffer."""
    if hasattr(index, "vectors") and isinstance(index, NumpyIndexFlatL2):
        # 45-byte FAISS IndexFlatL2 binary compatible header
        header = struct.pack("<4s i q 29s", b"IxF2", int(index.d), int(index.ntotal), b"\x00" * 29)
        vec_bytes = index.vectors.astype(np.float32).tobytes()
        full_bytes = header + vec_bytes
        return np.frombuffer(full_bytes, dtype=np.uint8)

    if _FAISS_AVAILABLE and faiss is not None:
        try:
            return faiss.serialize_index(index)
        except Exception:
            pass

    raise RuntimeError("Unable to serialize index: no compatible serialization method available.")


def deserialize_index(buffer: Union[np.ndarray, bytes]) -> Optional[Union[NumpyIndexFlatL2, object]]:
    """Deserializes uint8 buffer into an index object."""
    if isinstance(buffer, np.ndarray):
        raw_bytes = buffer.tobytes()
    elif isinstance(buffer, bytes):
        raw_bytes = buffer
    else:
        raw_bytes = bytes(buffer)

    if not raw_bytes:
        return None

    if _FAISS_AVAILABLE and faiss is not None:
        try:
            return faiss.deserialize_index(np.frombuffer(raw_bytes, dtype=np.uint8))
        except Exception:
            pass

    # Pure NumPy fallback deserializer
    if len(raw_bytes) >= 16:
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
