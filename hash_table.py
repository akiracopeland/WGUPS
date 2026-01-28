# Custom Hash Table (separate chaining + move-to-front) for package storage
# Key: Package ID (int). Value: PackageRecord dict with address, city, zip, deadline, weight, status, delivered_at.

class HashTable:
    def __init__(self, initial_capacity=128):
        self._buckets = [[] for _ in range(initial_capacity)]
        self._size = 0

    def __len__(self):
        return self._size

    def _index(self, key):
        return (hash(key) & 0x7fffffff) % len(self._buckets)

    def _rehash_if_needed(self):
        load = self._size / len(self._buckets)
        if load <= 0.75:
            return
        old = self._buckets
        self._buckets = [[] for _ in range(len(old) * 2)]
        self._size = 0
        for bucket in old:
            for (k, v) in bucket:
                self.put(k, v)

    def put(self, key, value):
        i = self._index(key)
        bucket = self._buckets[i]
        for j, (k, v) in enumerate(bucket):
            if k == key:
                bucket[j] = (key, value)
                if j > 0:
                    bucket[0], bucket[j] = bucket[j], bucket[0]  # move-to-front
                return
        bucket.append((key, value))
        if len(bucket) > 1:
            bucket[0], bucket[-1] = bucket[-1], bucket[0]
        self._size += 1
        self._rehash_if_needed()

    def get(self, key):
        i = self._index(key)
        bucket = self._buckets[i]
        for j, (k, v) in enumerate(bucket):
            if k == key:
                if j > 0:
                    bucket[0], bucket[j] = bucket[j], bucket[0]
                return v
        return None

    def remove(self, key):
        i = self._index(key)
        bucket = self._buckets[i]
        for j, (k, v) in enumerate(bucket):
            if k == key:
                del bucket[j]
                self._size -= 1
                return True
        return False

    # Helpers for screenshots/debug
    def first_n_buckets(self, n=10):
        return self._buckets[:n]

# --- Task A/B required functions ---

def ht_insert_package(store: HashTable, package_id: int, address: str, deadline: str,
                      city: str, zip_code: str, weight: float,
                      status: str, delivered_at) -> None:
    """Insert or update a package record in the custom hash table.
    This fulfills Task A: insertion by package ID with all required components.
    """
    record = {
        'address': address,
        'deadline': deadline,
        'city': city,
        'zip': zip_code,
        'weight': weight,
        'status': status,
        'delivered_at': delivered_at
    }
    store.put(package_id, record)

def ht_lookup_package(store: HashTable, package_id: int):
    """Lookup by package ID and return all required components.
    This fulfills Task B.
    Returns None if not found; otherwise returns the record dict.
    """
    return store.get(package_id)
