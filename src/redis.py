from typing import Dict
import redis


class RedisCache:
    def __init__(self):
        self.client = redis.Redis(host='127.0.0.1', port=6379, db=0)

    def setHash(self, key: str, hash: dict, expire: int = 3600) -> None:
        with self.client.pipeline() as pipe:
            pipe.hset(key, mapping=hash)
            pipe.expire(key, expire)
            pipe.execute()

    def getHash(self, key: str) -> Dict[bytes, bytes]:
        return self.client.hgetall(key)

    def deleteHash(self, key: str) -> None:
        self.client.delete(key)
