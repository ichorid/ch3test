import hashlib


def hash_str_to_int(s):
    return int(hashlib.sha256(s.encode('utf-8')).hexdigest(), 16) % 2 ** 32
