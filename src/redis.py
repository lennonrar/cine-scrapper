from typing import Optional
import redis


class RedisCache:
    def __init__(self):
        self.client = redis.Redis(host='127.0.0.1', port=6379, db=0)

    def setHash(self, key: str, hash: str | dict, expire: int = 3600):
        self.client.hset(key, mapping=hash)
        self.client.expire(key, expire)

    def getHash(self, key: str) -> Optional[str]:
        return self.client.hgetall(key)

    def deleteHash(self, key: str):
        self.client.hdel(key)
